"""
fix_notes_newlines.py

1. 修正 requirements_notes.json 中仍從錯誤位置開始的備注
   （理學院學士班_數學領域專長、機械工程學系三組）

2. 對全部 46 個系所的 raw_text 做換行正規化：
   只在標號前保留 \n，其他換行合併為空格。
   支援的標號格式：
     一、  二、  三、  ...（中文節號）
     1    2    3    ...（數字 + 空格）
     1.   2.   3.   ...（數字 + 句點）
     (1)  (2)  (3)  ...（括弧 + 阿拉伯數字）
     (一) (二) (三) ...（括弧 + 中文數字）
     ①   ②   ③   ...（圓圈數字）
     A.   B.   C.   ...（大寫字母 + 句點）
     a.   b.   c.   ...（小寫字母 + 句點）
"""
import pdfplumber, re, json

import os
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BASE = os.path.join(_ROOT, 'data', 'raw', '應修科目表')
OUTPUT = os.path.join(_ROOT, 'data', 'processed', 'requirements_notes.json')

# ─── 工具函式 ─────────────────────────────────────────────────

def get_text(pdf_path):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
    return '\n'.join(pages)

# 正規化後保留換行的行首模式
_ITEM_RE = re.compile(
    r'^(?:'
    r'[一二三四五六七八九十][、，。\s]'   # 一、 二、
    r'|\d+[\s\.]'                          # 1  或 1.
    r'|\d{1,2}(?!\d)'                      # 1-2 位數字後接非數字（如 1共同、2＊），排除3位以上數字
    r'|\(\d+[）)]'                          # (1) (1）
    r'|\([一二三四五六七八九十][）)]'       # (一) (一）
    r'|[①②③④⑤⑥⑦⑧⑨⑩]'             # ① ②
    r'|[A-Z][\.）、)]'                    # A. B. C.
    r'|[a-z][\.）、)]'                    # a. b. c.
    r')'
)

def is_item_start(line: str) -> bool:
    return bool(_ITEM_RE.match(line.strip()))

def normalize_newlines(text: str) -> str:
    """
    只在標號前保留 \\n，其他換行合併為空格。
    同時去除頁碼行（如 12-9-1）和孤立的 backslash。
    """
    result_lines: list[str] = []
    for raw_line in text.split('\n'):
        stripped = raw_line.strip()
        if not stripped:
            continue
        # 去掉頁碼行
        if re.match(r'^\d+-\d+(-\d+)?$', stripped):
            continue
        # 去掉孤立 backslash
        if stripped == '\\':
            continue
        # 去掉獨立的備註標籤行
        if re.fullmatch(r'備\s*[注註]?\s*', stripped):
            continue

        if not result_lines or is_item_start(stripped):
            result_lines.append(stripped)
        else:
            # 非標號行：合併到上一行
            # 若上一行是純數字（獨立項目號），加空格再接內容
            if re.fullmatch(r'\d+', result_lines[-1]):
                result_lines[-1] += ' ' + stripped
            else:
                result_lines[-1] += stripped

    return '\n'.join(result_lines)

def clean_notes_from_yi(text: str, start_re: str = r'^一[、，。\s]*共同必修') -> str:
    """從第一個「一、共同必修」行開始擷取，並去除備注標籤行"""
    lines = text.split('\n')
    start = 0
    for i, line in enumerate(lines):
        if re.match(start_re, line.strip()):
            start = i
            break
    result = []
    for ln in lines[start:]:
        s = ln.strip()
        if re.match(r'^\d+-\d+(-\d+)?$', s):
            continue
        if re.fullmatch(r'備\s*[注註]?\s*', s):
            continue
        # 行首備注標籤 → 去除（如 "備註 例:" → "例:"，"備註 二、" → "二、"）
        ln = re.sub(r'^備\s*[注註]\s+', '', ln)
        result.append(ln)
    return '\n'.join(result)

# ─── Step 1：修正起始位置 ──────────────────────────────────────

position_fixes: dict[str, str] = {}

# 理學院學士班_數學領域專長：有 1/2/3 三項，備注標籤嵌在第 2 項前
text = get_text(f'{BASE}/理學院/理學院學士班_數學領域專長_114.pdf')
lines = text.split('\n')
# 找第一個以 "1 A組等同" 開頭的行
start = 0
for i, ln in enumerate(lines):
    if re.match(r'^1\s+A組', ln.strip()):
        start = i
        break
raw_lines = []
for ln in lines[start:]:
    s = ln.strip()
    if re.match(r'^\d+-\d+(-\d+)?$', s):
        continue
    # 去掉 "備註 A組..." → "A組..."（備注標籤在第 2 項前）
    ln = re.sub(r'^備\s*[注註]\s+', '', ln)
    raw_lines.append(ln)
position_fixes['理學院學士班_數學領域專長'] = '\n'.join(raw_lines)

# 機械工程學系三組：都從 "一、共同必修" 開始
for group in ['設計與分析組', '光機電工程組', '先進材料與精密製造組']:
    text = get_text(f'{BASE}/工學院/機械工程學系_{group}_114.pdf')
    notes = clean_notes_from_yi(text, r'^一[、，。\s]*共同必修')
    position_fixes[f'機械工程學系_{group}'] = notes

# 數學系兩組：從 "一、共同必修" 開始（_數學科學組原本從 "二、" 開始；_計算與資料科學組有 "2本系..." 黏合問題）
for group in ['數學科學組', '計算與資料科學組']:
    text = get_text(f'{BASE}/理學院/數學系_{group}_114.pdf')
    position_fixes[f'數學系_{group}'] = clean_notes_from_yi(text, r'^一[、，。\s]*共同必修')

# 電機工程學系：只讀第一頁（後續頁都是課程流程圖）
with pdfplumber.open(f'{BASE}/資訊電機學院/電機工程學系_114.pdf') as _pdf:
    _page1 = _pdf.pages[0].extract_text() or ''
position_fixes['電機工程學系'] = clean_notes_from_yi(_page1, r'^一[、，。\s]*共同必修')

# ─── Step 2：讀取 JSON，套用位置修正 ──────────────────────────

with open(OUTPUT, 'r', encoding='utf-8') as f:
    data = json.load(f)

for dept, new_text in position_fixes.items():
    if dept in data:
        data[dept]['raw_text'] = new_text
        if data[dept].get('source') != 'image_manual':
            data[dept]['source'] = 'pdfplumber_fixed'
        print(f'[位置修正] {dept}')

# ─── Step 3：對全部條目做換行正規化 ────────────────────────────

for dept, entry in data.items():
    if entry.get('source') == 'image_manual':
        continue  # 手動輸入的不動
    original = entry.get('raw_text', '')
    normalized = normalize_newlines(original)
    if normalized != original:
        entry['raw_text'] = normalized
        if entry.get('source') == 'pdfplumber':
            entry['source'] = 'pdfplumber_fixed'

# ─── Step 4：去除所有條目開頭的備注標籤（含 image_manual）─────

for dept, entry in data.items():
    rt = entry.get('raw_text', '')
    # 去掉獨立備注行（如 "備注\n一、..."）
    new_rt = re.sub(r'^備\s*[注註]\s*\n', '', rt)
    # 去掉行首備注前綴（如 "備注 1 ..." → "1 ..."）
    new_rt = re.sub(r'^備\s*[注註]\s+', '', new_rt)
    if new_rt != rt:
        entry['raw_text'] = new_rt
        src = entry.get('source', '')
        if src == 'pdfplumber':
            entry['source'] = 'pdfplumber_fixed'
        print(f'[去備注開頭] {dept} (source={src})')

# ─── 儲存 ──────────────────────────────────────────────────────

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('\n✓ 全部完成，已寫入', OUTPUT)

# ─── 預覽結果 ──────────────────────────────────────────────────

print('\n── 修正後預覽 ──')
preview_depts = list(position_fixes.keys()) + ['電機工程學系', '財務金融學系', '客家語文暨社會科學學系_社政組']
for dept in preview_depts:
    if dept in data:
        preview = data[dept]['raw_text'][:250].replace('\n', ' | ')
        print(f'\n[{dept}]\n  {preview}')
