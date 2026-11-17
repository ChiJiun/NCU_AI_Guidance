"""
3a_extract_pdf_sections.py

從每份 PDF 抽取研究動機、方法、結論三段原文，
儲存至 data/processed/pdf_sections_raw.json。

執行（在 scripts/ 目錄下）：
    python 3a_extract_pdf_sections.py              # 全部
    python 3a_extract_pdf_sections.py --limit 20   # 只跑前 20 筆
    python 3a_extract_pdf_sections.py --report      # 跑完後印統計報告

依賴套件：
    pip install pymupdf tiktoken
"""

import os
import re
import sys
import json
import argparse
from collections import defaultdict

# ─────────────────────────────────────────
# 路徑設定
# ─────────────────────────────────────────
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.join(SCRIPT_DIR, '..', '..', '..')
PDF_BASE      = os.path.join(PROJECT_ROOT, 'data', 'raw', 'projects', '104-114')
PROJECTS_JSON = os.path.join(PROJECT_ROOT, 'data', 'processed', 'projects.json')
OUTPUT_JSON   = os.path.join(PROJECT_ROOT, 'data', 'processed', 'pdf_sections_raw.json')

# ─────────────────────────────────────────
# 各欄位搜尋關鍵字
# ─────────────────────────────────────────
SECTION_KEYWORDS = {
    'motivation': '研究動機,研究目的,研究動機與目的,研究背景,前言,緒論,Introduction,研究問題',
    'method':     '研究方法,研究設計,研究流程,研究架構,方法論,Methodology,Method,研究步驟',
    'result':     '研究結果,研究結論,結論,結果與討論,研究發現,Conclusion,Discussion,結果,結語,總結,小結,研究總結,綜述',
}

MAX_CHARS = 2500  # 每段最多保留的字元數（超過截斷）


# ─────────────────────────────────────────
# Token 計算（使用 tiktoken；若未安裝則用字元數估算）
# ─────────────────────────────────────────
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))

except ImportError:
    print("[警告] tiktoken 未安裝，改用字元數 ÷ 1.5 估算 token 數。建議：pip install tiktoken")

    def count_tokens(text: str) -> int:
        return int(len(text) / 1.5)


# ─────────────────────────────────────────
# PDF 段落抽取（回傳字串，不寫磁碟）
# ─────────────────────────────────────────
def extract_section(pdf_path: str, target_title: str, max_chars: int = MAX_CHARS) -> tuple[str, str]:
    """
    回傳 (extracted_text, found_heading)。
    found_heading 為實際比對到的標題文字，找不到時為空字串。
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("請先安裝 PyMuPDF：pip install pymupdf")

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return '', ''

    # 找 body 字體大小
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
        return '', ''

    body_size = max(font_counts, key=font_counts.get)

    # 收集所有文字
    all_texts = []
    for page_num, page in enumerate(doc):
        try:
            for b in page.get_text("dict")["blocks"]:
                if b.get('type') == 0:
                    for l in b.get("lines", []):
                        for s in l.get("spans", []):
                            text = s['text'].replace('\n', '')
                            if text.strip():
                                all_texts.append((page_num + 1, round(s['size'], 2),
                                                  text, s['font'], s['flags']))
                    all_texts.append((page_num + 1, body_size, "\n", "end_of_block", 0))
        except Exception:
            pass

    target_set = {t.strip() for t in target_title.split(',')}

    heading_pattern = re.compile(
        r'^([一二三四五六七八九十]+、|\([一二三四五六七八九十]+\)|\d+\.\d+|\d+、|\d+\.|'
        r'第[一二三四五六七八九十]+章|I{1,3}\.|IV\.|V\.|VI{0,3}\.|IX\.|X\.)'
    )
    stop_keywords = ['文獻回顧', '研究方法', '結果與討論', '結論', '參考文獻', '致謝',
                     'RESEARCH METHODS', 'METHOD', 'CONCLUSION', 'REFERENCES']

    is_recording = False
    found_heading = ''
    collected = []

    for i, (page_num, size, text, font, flags) in enumerate(all_texts):
        font_lower = font.lower()
        is_bold   = bool(flags & 16) or any(k in font_lower for k in ('bold', 'heavy', 'black'))
        is_large  = size > body_size + 0.5
        is_heading = is_bold or is_large

        if font != "end_of_block":
            stripped = text.strip()
            if (heading_pattern.match(stripped) or
                    any(kw in text for kw in stop_keywords)) and len(text) < 35:
                if not re.match(r'^\d+(\.\d+)?$', stripped):
                    is_heading = True

        matched = next((t for t in target_set if t in text), None)

        if matched:
            stripped = text.strip()
            # 判斷是否為清單式標題，如「一、研究動機」「（三）研究方法」
            list_heading = re.match(r'^[（(]?[一二三四五六七八九十百\d]+[、）)．]\s*', stripped)
            # 判斷是否為英文章節標題，如「1.1 Introduction」
            eng_heading  = re.match(r'^\d+(\.\d+)?\s+\w', stripped)

            # 條件一：文字太長（> 30 字）→ 內文句子，非標題
            too_long = len(stripped) > 30
            # 條件二：包含句子標點 → 內文句子
            has_punct = any(c in stripped for c in ('，', '。', '；'))
            # 條件三：以連接詞開頭 → 明顯是句子中間
            starts_mid = stripped[:1] in ('、', '的', '了', '也', '後', '並', '且')

            if (too_long or has_punct or starts_mid) and not list_heading and not eng_heading:
                matched = None

        if is_heading or matched:
            if matched:
                # TOC 檢查
                is_toc = False
                for j in range(1, 11):
                    if i - j >= 0 and '目錄' in all_texts[i - j][2]:
                        is_toc = True
                        break
                if not is_toc:
                    if text.count('.') > 4 or text.count('．') > 4 or '…' in text:
                        is_toc = True
                    else:
                        for j in range(1, 4):
                            if i + j < len(all_texts):
                                nt = all_texts[i + j][2]
                                if nt.count('.') > 3 or '...' in nt or '…' in nt:
                                    is_toc = True
                                    break
                if is_toc:
                    continue
                is_recording = True
                found_heading = text.strip()
            elif is_recording:
                break  # 遇到另一個標題，停止
        else:
            if is_recording:
                if font == "end_of_block":
                    collected.append('\n')
                else:
                    collected.append(text)
                if sum(len(c) for c in collected) >= max_chars:
                    break

    return ''.join(collected).strip(), found_heading


# ─────────────────────────────────────────
# 統計報告
# ─────────────────────────────────────────
def print_report(records: list):
    total = len(records)
    img_only = sum(1 for r in records if r['is_image_pdf'])

    field_stats = {}
    for field in SECTION_KEYWORDS:
        found    = sum(1 for r in records if r[f'{field}_raw'])
        tokens   = [r[f'{field}_tokens'] for r in records if r[f'{field}_raw']]
        field_stats[field] = {
            'found':      found,
            'not_found':  total - found,
            'found_pct':  found / total * 100 if total else 0,
            'avg_tokens': int(sum(tokens) / len(tokens)) if tokens else 0,
            'max_tokens': max(tokens) if tokens else 0,
            'over_2000':  sum(1 for t in tokens if t > 2000),
            'over_3000':  sum(1 for t in tokens if t > 3000),
        }

    print("\n" + "=" * 60)
    print(f"  抽取統計報告  (共 {total} 份 PDF)")
    print("=" * 60)
    print(f"  純圖片 PDF（無法抽取文字）：{img_only} 份")
    print()

    for field, s in field_stats.items():
        print(f"  [{field}]")
        print(f"    找到：{s['found']} 份 ({s['found_pct']:.1f}%) ｜ 未找到：{s['not_found']} 份")
        print(f"    平均 tokens：{s['avg_tokens']} ｜ 最大 tokens：{s['max_tokens']}")
        if s['over_2000']:
            print(f"    ⚠ 超過 2000 tokens：{s['over_2000']} 份")
        if s['over_3000']:
            print(f"    ⚠ 超過 3000 tokens：{s['over_3000']} 份（送 OpenAI 前會截斷）")
        print()

    # 印出完全沒抽到任何段落的 PDF 清單
    empty = [r for r in records if not any(r[f'{f}_raw'] for f in SECTION_KEYWORDS)]
    if empty:
        print(f"  ⚠ 三段均未找到（共 {len(empty)} 份）：")
        for r in empty[:20]:
            print(f"    [{r['id']}] {r['department']} | {r['title'][:40]}")
        if len(empty) > 20:
            print(f"    ... 以及其他 {len(empty) - 20} 份")
    print("=" * 60)


# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit',  type=int, default=0, help='限制處理筆數（0 = 全部）')
    parser.add_argument('--report', action='store_true', help='印出統計報告')
    args = parser.parse_args()

    with open(PROJECTS_JSON, 'r', encoding='utf-8') as f:
        projects = json.load(f)

    # 斷點續跑：已處理的跳過
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
            records = json.load(f)
        done_ids = {r['id'] for r in records}
        print(f"發現已有 {len(records)} 筆，繼續補跑...")
    else:
        records = []
        done_ids = set()

    limit = args.limit if args.limit > 0 else len(projects)
    processed = 0

    for proj in projects:
        if processed >= limit:
            break

        proj_id = proj['id']
        if proj_id in done_ids:
            continue

        pdf_rel  = proj.get('pdfPath', '')
        pdf_path = os.path.normpath(os.path.join(PDF_BASE, pdf_rel))
        title    = proj.get('title', '')
        dept     = proj.get('department', '')

        if not os.path.exists(pdf_path):
            print(f"[{proj_id}] 找不到 PDF，跳過：{pdf_rel}")
            continue

        print(f"[{proj_id}] {dept} | {title[:35]}...", end='  ')

        # 判斷是否為純圖片 PDF（第一頁完全抓不到文字）
        try:
            import fitz
            doc = fitz.open(pdf_path)
            first_page_text = doc[0].get_text().strip() if len(doc) > 0 else ''
            is_image_pdf = len(first_page_text) < 10
        except Exception:
            is_image_pdf = True

        record = {
            'id':           proj_id,
            'year':         str(proj.get('year', '')),
            'department':   dept,
            'studentName':  proj.get('studentName', ''),
            'title':        title,
            'pdfPath':      pdf_rel,
            'is_image_pdf': is_image_pdf,
        }

        status_parts = []
        for field, keywords in SECTION_KEYWORDS.items():
            if is_image_pdf:
                text, heading = '', ''
            else:
                text, heading = extract_section(pdf_path, keywords)

            tokens = count_tokens(text) if text else 0
            record[f'{field}_raw']     = text
            record[f'{field}_heading'] = heading   # 實際比對到的標題（方便除錯）
            record[f'{field}_tokens']  = tokens

            if text:
                status_parts.append(f"{field}={tokens}tok")
            else:
                status_parts.append(f"{field}=未找到")

        print(' | '.join(status_parts))

        records.append(record)
        done_ids.add(proj_id)
        processed += 1

        # 每筆寫回
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\n完成！共處理 {processed} 筆，總計 {len(records)} 筆已存入：\n  {OUTPUT_JSON}")

    if args.report or True:  # 預設都印報告
        print_report(records)


if __name__ == '__main__':
    main()
