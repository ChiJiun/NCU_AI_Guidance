"""
3c_extract_abstract.py

從每份 PDF 抽取摘要（Abstract）與關鍵字（Keywords），
儲存至 data/processed/pdf_abstracts.json。

執行（在 scripts/ 目錄下）：
    python 3c_extract_abstract.py              # 全部
    python 3c_extract_abstract.py --limit 10   # 只跑前 10 筆
    python 3c_extract_abstract.py --show 3     # 印出前 3 筆的原文內容

依賴套件：
    pip install pymupdf tiktoken
"""

import os
import re
import json
import argparse

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.join(SCRIPT_DIR, '..', '..', '..')
PDF_BASE      = os.path.join(PROJECT_ROOT, 'data', 'raw', 'projects', '104-114')
PROJECTS_JSON = os.path.join(PROJECT_ROOT, 'data', 'processed', 'projects.json')
OUTPUT_JSON   = os.path.join(PROJECT_ROOT, 'data', 'processed', 'pdf_abstracts.json')

# 摘要標題關鍵字（優先順序由前到後）
ABSTRACT_KEYWORDS = ['摘要', 'Abstract', 'ABSTRACT', '中文摘要', '英文摘要', '研究摘要',
                     '中英文摘要', '摘 要', '大綱', '概要', 'Summary', 'SUMMARY',
                     '題目敘述',   # CS 系報告格式：一、題目敘述
                     '前言',       # 最後備援：沒有摘要但有前言的論文
                     ]

# 關鍵字標題關鍵字
KEYWORD_KEYWORDS  = ['關鍵字', '關鍵詞', 'Keywords', 'Key words', 'KEYWORDS', '索引詞']

# 摘要最大抓取字元數（摘要通常 300-800 字）
MAX_ABSTRACT_CHARS = 2000


# ─────────────────────────────────────────
# Token 計算
# ─────────────────────────────────────────
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except ImportError:
    def count_tokens(text: str) -> int:
        return int(len(text) / 1.5)


# ─────────────────────────────────────────
# 從文字串列中解析關鍵字（支援跨行、雙語）
# ─────────────────────────────────────────
def parse_keywords(text: str) -> list[str]:
    """
    從「關鍵字：A、B、C」或「Keywords: A, B, C」格式解析關鍵字。
    支援跨行（text 可能已事先合併多行）。
    """
    # 移除標題前綴，支援中英文所有變體
    kw_pattern = '|'.join(re.escape(k) for k in KEYWORD_KEYWORDS)
    cleaned = re.sub(rf'^({kw_pattern})[：:\s]*', '', text.strip(), flags=re.IGNORECASE)
    # 移除行尾的頁碼或 Roman numerals
    cleaned = re.sub(r'\s+[IVXivx]+\s*$', '', cleaned).strip()
    # 分割：中文用 、，；　，英文用 , ;
    parts = re.split(r'[、，,；;\u3000\s]+', cleaned)
    keywords = [re.sub(r'[。，、；：！？\.\s]+$', '', p.strip())
                for p in parts if 2 <= len(p.strip()) <= 25]
    keywords = [k for k in keywords if len(k) >= 2]
    return keywords


def is_toc_line(i: int, all_texts: list) -> bool:
    """檢查是否為目錄行（後面接點點點或頁碼）"""
    for j in range(1, 4):
        if i + j < len(all_texts):
            nt = all_texts[i + j]['text']
            if nt.count('.') > 3 or '...' in nt or '…' in nt:
                return True
    return False


# ─────────────────────────────────────────
# 主要抽取函式（兩趟掃描）
# ─────────────────────────────────────────
def extract_abstract_and_keywords(pdf_path: str) -> dict:
    """
    策略：
    1. 掃描前 15 頁，標記所有「摘要/Abstract」和「關鍵字/Keywords」的位置
    2. 優先取中文摘要；若只有英文摘要才取英文
    3. 優先取「中文關鍵詞」；若只有 Keywords 才取英文關鍵字
    4. 關鍵字可能跨行，需合併後再解析
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("請先安裝 PyMuPDF：pip install pymupdf")

    result = {
        'abstract_raw':     '',
        'abstract_tokens':  0,
        'abstract_heading': '',
        'keywords':         [],
        'keyword_heading':  '',
        'has_abstract':     False,
        'has_keywords':     False,
    }

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return result

    # ── 找 body 字體大小（全文掃描）──
    font_counts: dict = {}
    for page in doc:
        try:
            for b in page.get_text("dict")["blocks"]:
                if b.get('type') == 0:
                    for l in b.get("lines", []):
                        for s in l.get("spans", []):
                            sz = round(s['size'], 2)
                            font_counts[sz] = font_counts.get(sz, 0) + len(s['text'].strip())
        except Exception:
            pass

    if not font_counts:
        return result

    body_size = max(font_counts, key=font_counts.get)

    # ── 收集前 15 頁所有文字 ──
    all_texts = []
    for page_num in range(min(len(doc), 15)):
        page = doc[page_num]
        try:
            for b in page.get_text("dict")["blocks"]:
                if b.get('type') == 0:
                    for l in b.get("lines", []):
                        for s in l.get("spans", []):
                            t = s['text'].replace('\n', '')
                            if t.strip():
                                all_texts.append({
                                    'page':  page_num + 1,
                                    'size':  round(s['size'], 2),
                                    'text':  t,
                                    'font':  s['font'],
                                    'flags': s['flags'],
                                })
                    all_texts.append({'page': page_num + 1, 'size': body_size,
                                      'text': '\n', 'font': 'end_of_block', 'flags': 0})
        except Exception:
            pass

    # ── 合併相鄰短 span（處理「摘 要」被拆成兩個 span 的情況）──
    merged = []
    i = 0
    while i < len(all_texts):
        span = all_texts[i]
        if span['font'] == 'end_of_block':
            merged.append(span)
            i += 1
            continue
        # 若當前 span 很短（≤ 3字），嘗試與後續短 span 合併（同頁、不跨 block）
        if len(span['text'].strip()) <= 3:
            combined_text  = span['text']
            combined_size  = span['size']
            combined_font  = span['font']
            combined_flags = span['flags']
            j = i + 1
            while j < len(all_texts):
                nxt = all_texts[j]
                if nxt['font'] == 'end_of_block':
                    break
                if nxt['page'] != span['page']:
                    break
                if len(nxt['text'].strip()) <= 3:
                    combined_text += nxt['text']
                    j += 1
                    if len(combined_text.strip()) > 6:  # 已夠長就停
                        break
                else:
                    # 下一個 span 較長，不併入（避免把短標題和正文合在一起）
                    break
            merged.append({'page': span['page'], 'size': combined_size,
                           'text': combined_text, 'font': combined_font,
                           'flags': combined_flags})
            i = j
        else:
            merged.append(span)
            i += 1
    all_texts = merged

    n = len(all_texts)

    # ── 第一趟：找出所有關鍵字行（位置不固定，可能在摘要前或後）──
    # 收集：[(index, 'zh'|'en', raw_text)]
    kw_zh_markers = ['關鍵字', '關鍵詞', '中文關鍵詞', '中文關鍵字']
    kw_en_markers = ['Keywords', 'KEYWORDS', 'Key words']
    keyword_hits = []  # (idx, lang, text)

    for i, span in enumerate(all_texts):
        if span['font'] == 'end_of_block':
            continue
        stripped = span['text'].strip()
        lang = None
        for kw in kw_zh_markers:
            if stripped.startswith(kw) or (kw + '：') in stripped or (kw + ':') in stripped:
                lang = 'zh'
                break
        if lang is None:
            for kw in kw_en_markers:
                if stripped.startswith(kw) or (kw + ':') in stripped or (kw + '：') in stripped:
                    lang = 'en'
                    break
        if lang:
            # 收集這一行 + 下一行（處理跨行關鍵字）
            combined = stripped
            for j in range(1, 4):
                if i + j < n and all_texts[i + j]['font'] != 'end_of_block':
                    next_text = all_texts[i + j]['text'].strip()
                    # 如果下一行看起來像關鍵字延續（有頓號、逗號，且沒有新的標題）
                    if re.search(r'[、，,]', next_text) and len(next_text) < 80:
                        combined += next_text
                    else:
                        break
                else:
                    break
            keyword_hits.append((i, lang, combined))

    # ── 解析關鍵字（優先中文）──
    zh_hits = [(i, t) for i, lang, t in keyword_hits if lang == 'zh']
    en_hits = [(i, t) for i, lang, t in keyword_hits if lang == 'en']

    chosen_kw_idx  = -1
    chosen_kw_text = ''
    if zh_hits:
        chosen_kw_idx, chosen_kw_text = zh_hits[0]
    elif en_hits:
        chosen_kw_idx, chosen_kw_text = en_hits[0]

    if chosen_kw_text:
        result['keyword_heading'] = chosen_kw_text[:80]
        result['keywords']        = parse_keywords(chosen_kw_text)
        result['has_keywords']    = bool(result['keywords'])

    # ── 第二趟：找摘要（優先中文摘要）──
    # 直接使用頂層 ABSTRACT_KEYWORDS，分中英文順序
    zh_abstract_kws = [k for k in ABSTRACT_KEYWORDS if not k.isascii()]
    en_abstract_kws = [k for k in ABSTRACT_KEYWORDS if k.isascii()]

    def find_abstract(kw_list: list) -> tuple[int, str]:
        """找第一個符合的摘要標題，回傳 (index, heading)"""
        import unicodedata
        for i, span in enumerate(all_texts):
            if span['font'] == 'end_of_block':
                continue
            stripped  = span['text'].strip()
            # NFKC 正規化：處理 CJK 異體字（⽬→目）和全形/半形差異
            normalized = unicodedata.normalize('NFKC', stripped).replace(' ', '').replace('\u3000', '')
            for kw in kw_list:
                kw_norm = unicodedata.normalize('NFKC', kw).replace(' ', '')
                # 條件：標題包含關鍵字，且整行不超過 30 字（避免誤抓內文句子）
                if kw_norm in normalized and len(normalized) <= 30:
                    if not is_toc_line(i, all_texts):
                        return i, stripped
        return -1, ''

    abs_idx, abs_heading = find_abstract(zh_abstract_kws)
    if abs_idx == -1:
        abs_idx, abs_heading = find_abstract(en_abstract_kws)

    # ── 從摘要標題之後錄製正文，遇到關鍵字行或下一個大標題停止 ──
    if abs_idx >= 0:
        result['abstract_heading'] = abs_heading
        abstract_parts = []
        stop_headings  = set(zh_abstract_kws + en_abstract_kws + ['目錄', 'Table of Contents',
                              '致謝', 'Acknowledgement', '目次'])

        for i in range(abs_idx + 1, n):
            span    = all_texts[i]
            text    = span['text']
            font    = span['font']
            size    = span['size']
            flags   = span['flags']
            stripped = text.strip()

            if font == 'end_of_block':
                abstract_parts.append('\n')
                continue

            # 遇到關鍵字行 → 停止
            if i == chosen_kw_idx or any(stripped.startswith(kw) for kw in
                                         kw_zh_markers + kw_en_markers):
                break

            # 遇到下一個大標題 → 停止
            font_lower = font.lower()
            is_bold    = bool(flags & 16) or any(k in font_lower for k in ('bold', 'heavy', 'black'))
            is_large   = size > body_size + 0.5
            if (is_bold or is_large) and len(stripped) <= 20:
                if stripped in stop_headings or (
                    sum(len(p) for p in abstract_parts) > 80
                ):
                    break

            abstract_parts.append(text)
            if sum(len(p) for p in abstract_parts) >= MAX_ABSTRACT_CHARS:
                break

        abstract_text = ''.join(abstract_parts).strip()
        # 清除殘留的關鍵字行
        for kw in kw_zh_markers + kw_en_markers:
            abstract_text = re.sub(rf'({kw})[：:\s].*$', '', abstract_text,
                                   flags=re.MULTILINE).strip()

        result['abstract_raw']    = abstract_text
        result['abstract_tokens'] = count_tokens(abstract_text) if abstract_text else 0
        result['has_abstract']    = bool(abstract_text)

    return result


# ─────────────────────────────────────────
# 統計報告
# ─────────────────────────────────────────
def print_report(records: list):
    total         = len(records)
    has_abstract  = sum(1 for r in records if r['has_abstract'])
    has_keywords  = sum(1 for r in records if r['has_keywords'])
    both_missing  = sum(1 for r in records if not r['has_abstract'] and not r['has_keywords'])
    tokens        = [r['abstract_tokens'] for r in records if r['has_abstract']]
    kw_counts     = [len(r['keywords']) for r in records if r['has_keywords']]

    print("\n" + "=" * 60)
    print(f"  摘要抽取統計報告  (共 {total} 份 PDF)")
    print("=" * 60)
    print(f"  找到摘要：{has_abstract} 份 ({has_abstract/total*100:.1f}%)")
    print(f"  找到關鍵字：{has_keywords} 份 ({has_keywords/total*100:.1f}%)")
    print(f"  兩者皆無：{both_missing} 份")

    if tokens:
        print(f"\n  [摘要 tokens]")
        print(f"    平均：{int(sum(tokens)/len(tokens))} ｜ 最小：{min(tokens)} ｜ 最大：{max(tokens)}")
        over_800  = sum(1 for t in tokens if t > 800)
        over_1500 = sum(1 for t in tokens if t > 1500)
        if over_800:  print(f"    超過 800 tokens：{over_800} 份")
        if over_1500: print(f"    超過 1500 tokens：{over_1500} 份")

    if kw_counts:
        print(f"\n  [關鍵字數量]")
        print(f"    平均：{sum(kw_counts)/len(kw_counts):.1f} 個 ｜ 最多：{max(kw_counts)} 個")

    # 沒找到摘要的列表
    no_abstract = [r for r in records if not r['has_abstract']]
    if no_abstract:
        print(f"\n  ⚠ 找不到摘要（共 {len(no_abstract)} 份）：")
        for r in no_abstract[:15]:
            print(f"    [{r['id']}] {r['department']} | {r['title'][:35]}")
        if len(no_abstract) > 15:
            print(f"    ... 以及其他 {len(no_abstract)-15} 份")

    print("=" * 60)


# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0, help='限制處理筆數（0 = 全部）')
    parser.add_argument('--show',  type=int, default=0, help='印出前 N 筆的摘要原文')
    args = parser.parse_args()

    with open(PROJECTS_JSON, 'r', encoding='utf-8') as f:
        projects = json.load(f)

    # 斷點續跑
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
            records = json.load(f)
        done_ids = {r['id'] for r in records}
        print(f"發現已有 {len(records)} 筆，繼續補跑...")
    else:
        records = []
        done_ids = set()

    limit = args.limit if args.limit > 0 else len(projects)
    shown = 0
    processed = 0

    for proj in projects:
        if processed >= limit:
            break

        proj_id = proj['id']
        if proj_id in done_ids:
            continue

        pdf_rel  = proj.get('pdfPath', '')
        pdf_path = os.path.normpath(os.path.join(PDF_BASE, pdf_rel))

        if not os.path.exists(pdf_path):
            print(f"[{proj_id}] 找不到 PDF，跳過")
            continue

        data = extract_abstract_and_keywords(pdf_path)

        record = {
            'id':               proj_id,
            'year':             str(proj.get('year', '')),
            'department':       proj.get('department', ''),
            'studentName':      proj.get('studentName', ''),
            'title':            proj.get('title', ''),
            'pdfPath':          pdf_rel,
            **data,
        }
        records.append(record)
        done_ids.add(proj_id)
        processed += 1

        ab_status  = f"摘要={data['abstract_tokens']}tok" if data['has_abstract']  else "摘要=未找到"
        kw_status  = f"關鍵字={len(data['keywords'])}個"  if data['has_keywords']  else "關鍵字=未找到"
        print(f"[{proj_id}] {proj.get('department','')} | {proj.get('title','')[:30]}...  {ab_status} | {kw_status}")

        if args.show and shown < args.show and data['has_abstract']:
            print(f"  ── 摘要原文 ──")
            print(f"  {data['abstract_raw'][:400]}")
            if data['keywords']:
                print(f"  ── 關鍵字 ──")
                print(f"  {data['keywords']}")
            print()
            shown += 1

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\n完成！共 {len(records)} 筆已存入：\n  {OUTPUT_JSON}")
    print_report(records)


if __name__ == '__main__':
    main()
