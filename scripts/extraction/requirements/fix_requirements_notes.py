"""
修正 requirements_notes.json 中備注文字從錯誤位置開始或被截斷的問題。
"""
import pdfplumber, re, json

import os
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BASE = os.path.join(_ROOT, 'data', 'raw', '應修科目表')
OUTPUT = os.path.join(_ROOT, 'data', 'processed', 'requirements_notes.json')

def get_all_text(pdf_path):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
    return '\n'.join(pages)

def clean_notes(text, start_pattern=r'^一[\s、,，。]|^一 、'):
    """從「一、共同必修」開始提取，去除頁碼"""
    lines = text.split('\n')
    start = 0
    for i, line in enumerate(lines):
        if re.match(start_pattern, line.strip()):
            start = i
            break

    result_lines = []
    for line in lines[start:]:
        stripped = line.strip()
        # 去掉頁碼行 (如 12-19-1 或 12-7)
        if re.match(r'^\d+-\d+(-\d+)?$', stripped):
            continue
        # 去掉末尾的孤立 backslash
        if stripped == chr(92):
            continue
        # 去掉獨立的 "備註" 行（它是表格欄位標籤）
        if re.fullmatch(r'備\s*[注註]?\s*', stripped):
            continue
        result_lines.append(line)

    return '\n'.join(result_lines).strip()

def clean_beinote_inline(text):
    """把行首 '備註 N' / '備 N' / '註 N' → 'N'"""
    text = re.sub(r'^備\s*[注註]\s+(\d)', r'\1', text, flags=re.MULTILINE)
    text = re.sub(r'^備\s+(\d)', r'\1', text, flags=re.MULTILINE)
    text = re.sub(r'^[注註]\s+(\d)', r'\1', text, flags=re.MULTILINE)
    return text

fixes = {}

# ── 1. 電機工程學系 ──
text = get_all_text(f'{BASE}/資訊電機學院/電機工程學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
fixes['電機工程學系'] = notes

# ── 2. 物理學系 ──
text = get_all_text(f'{BASE}/理學院/物理學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
# 修正 "業界實習\n備註 I / II" 拼回
notes = re.sub(r'業界實習\n備\s*[注註]\s*', '業界實習', notes)
fixes['物理學系'] = notes

# ── 3. 光電科學與工程學系 ──
text = get_all_text(f'{BASE}/理學院/光電科學與工程學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
fixes['光電科學與工程學系'] = notes

# ── 4. 化學學系 ──
text = get_all_text(f'{BASE}/理學院/化學學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
fixes['化學學系'] = notes

# ── 5. 化學工程與材料工程學系 ──
text = get_all_text(f'{BASE}/工學院/化學工程與材料工程學系_114.pdf')
notes = clean_notes(text)
# 移除嵌入的 "備註" 標籤行並把前後行合併
lines_n = notes.split('\n')
cleaned = []
skip_next = False
for i, ln in enumerate(lines_n):
    if skip_next:
        skip_next = False
        continue
    if re.fullmatch(r'\s*備\s*[注註]?\s*', ln.strip()):
        if cleaned and i + 1 < len(lines_n):
            cleaned[-1] = cleaned[-1] + lines_n[i + 1]
            skip_next = True
        continue
    cleaned.append(ln)
fixes['化學工程與材料工程學系'] = '\n'.join(cleaned).strip()

# ── 6 & 7. 客家語文暨社會科學學系 ──
for suffix in ['社政組', '語文組']:
    fname = f'客家語文暨社會科學學系_{suffix}'
    text = get_all_text(f'{BASE}/客家學院/客家語文暨社會科學學系_{suffix}_114.pdf')
    notes = clean_notes(text)
    notes = clean_beinote_inline(notes)
    # 去掉 "註 二、" → "二、"（欄位標籤殘留）
    notes = re.sub(r'^[注註]\s+(二[\s、,，。])', r'\1', notes, flags=re.MULTILINE)
    fixes[fname] = notes

# ── 8. 工學院學士班 ──
text = get_all_text(f'{BASE}/工學院/工學院學士班_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
notes = re.sub(r'\n12-13\n', '\n', notes)
fixes['工學院學士班'] = notes.strip()

# ── 9-11. 工學院學士班各專長 ──
def join_chinese(s):
    """把漢字之間殘留的空格移除（由備註欄位移除後留下的換行/空白）"""
    return re.sub(r'([\u4e00-\u9fff、。：；！？，（）【】〔〕「」『』])\s+([\u4e00-\u9fff、。：；！？，（）【】〔〕「」『』])', r'\1\2', s)

for fname_part in ['永續防災專長', '綠色科技專長', '能源材料專長']:
    text = get_all_text(f'{BASE}/工學院/工學院學士班_{fname_part}_114.pdf')
    # 找第二個 "領域必修科目計" 開頭的句子（第一個是表格欄位）
    matches = list(re.finditer(r'領域必修科目計', text))
    start = matches[-1].start() if matches else 0
    snippet = text[start:]
    # 去掉 "備註" 標籤行
    snippet = re.sub(r'\n備\s*[注註]\s*\n', ' ', snippet)
    snippet = re.sub(r'\s*備\s*[注註]\s*', ' ', snippet)
    # 合併換行符和多餘空白
    raw = re.sub(r'\s+', ' ', snippet).strip()
    # 漢字間空格消除
    raw = join_chinese(raw)
    # 截到第一個 "。" 為止（整句）
    m = re.search(r'。', raw)
    if m:
        raw = raw[:m.start()+1]
    fixes[f'工學院學士班_{fname_part}'] = raw

# ── 12. 數學系_計算與資料科學組 ──
text = get_all_text(f'{BASE}/理學院/數學系_計算與資料科學組_114.pdf')
# 找真正的 "一、共同必修" 行（跳過 "一 資料科學..." 課程行）
lines = text.split('\n')
start = 0
for i, ln in enumerate(lines):
    stripped = ln.strip()
    # 精確匹配 "一、共同必修"
    if re.match(r'^一[、,，。\s]*共同必修', stripped):
        start = i
        break
notes = '\n'.join(lines[start:])
notes = clean_notes(notes, r'^一')  # 從這裡開始，不再需要重找
notes = clean_beinote_inline(notes)
fixes['數學系_計算與資料科學組'] = notes

# ── 13-15. 理學院學士班各領域專長 ──
for spec in ['化學領域專長', '物理領域專長', '生命科學領域專長']:
    fname = f'理學院學士班_{spec}'
    text = get_all_text(f'{BASE}/理學院/理學院學士班_{spec}_114.pdf')
    lines = text.split('\n')
    result = []
    in_notes = False
    for ln in lines:
        stripped = ln.strip()
        # 去掉頁碼
        if re.match(r'^\d+-\d+(-\d+)?$', stripped):
            continue
        # 去掉孤立的 backslash
        if stripped == chr(92):
            continue
        # "備 1" → 開始備注, "1 第一..."
        if re.match(r'^備\s+\d', stripped):
            in_notes = True
            result.append(re.sub(r'^備\s+', '', stripped))
            continue
        # "備" 孤立
        if re.fullmatch(r'備', stripped):
            in_notes = True
            continue
        # "註 2" → "2"
        if re.match(r'^[注註]\s+\d', stripped):
            result.append(re.sub(r'^[注註]\s+', '', stripped))
            continue
        if in_notes:
            result.append(ln)
    fixes[fname] = '\n'.join(result).strip()

# ── 16. 財務金融學系 ──
text = get_all_text(f'{BASE}/管理學院/財務金融學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
# 修正 pdfplumber 多欄誤讀 item 3（正確文字：選修「進修英文」取得之學分，不列入本系之畢業學分總數。）
notes = re.sub(
    r'3\s*\(選1[）)].+?本系之畢業學分總數。',
    '3 選修「進修英文」取得之學分，不列入本系之畢業學分總數。',
    notes
)
fixes['財務金融學系'] = notes

# ── 17. 資訊管理學系 ──
text = get_all_text(f'{BASE}/管理學院/資訊管理學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
fixes['資訊管理學系'] = notes

# ── 18. 資訊工程學系 ──
text = get_all_text(f'{BASE}/資訊電機學院/資訊工程學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
fixes['資訊工程學系'] = notes

# ── 19. 資訊電機學院學士班_網路工程專長 ──
text = get_all_text(f'{BASE}/資訊電機學院/資訊電機學院學士班_網路工程專長_114.pdf')
# 找 "1.選擇本專長" 開始的備注
m = re.search(r'(1\.\s*選擇本專長.*)', text, re.DOTALL)
if m:
    raw = m.group(1)
    # 移除嵌入的 "備註 " 標籤
    raw = re.sub(r'\n備\s*[注註]\s*', '\n', raw)
    # 去掉頁碼行
    raw = re.sub(r'\n12-\d+(-\d+)?\s*$', '', raw, flags=re.MULTILINE).strip()
    # 合併跨行漢字
    raw = join_chinese(raw)
    fixes['資訊電機學院學士班_網路工程專長'] = raw
else:
    fixes['資訊電機學院學士班_網路工程專長'] = text.strip()

# ── 20. 經濟學系 ──
text = get_all_text(f'{BASE}/管理學院/經濟學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
fixes['經濟學系'] = notes

# ── 21. 通訊工程學系 ──
text = get_all_text(f'{BASE}/資訊電機學院/通訊工程學系_114.pdf')
notes = clean_notes(text)
notes = clean_beinote_inline(notes)
# 去掉後續流程圖部分
m2 = re.search(r'\n電子類別\n', notes)
if m2:
    notes = notes[:m2.start()].strip()
fixes['通訊工程學系'] = notes

# ── 印出預覽 ──
for dept in sorted(fixes.keys()):
    preview = fixes[dept][:150].replace('\n', ' | ')
    print(f'[{dept}]\n  {preview}\n')

# ── 寫入 JSON ──
with open(OUTPUT, 'r', encoding='utf-8') as f:
    data = json.load(f)

updated = []
for dept, new_text in fixes.items():
    if dept in data:
        old_text = data[dept].get('raw_text', '')
        data[dept]['raw_text'] = new_text
        # 若原本是 pdfplumber 來源，保留
        if data[dept].get('source') != 'image_manual':
            data[dept]['source'] = 'pdfplumber_fixed'
        updated.append(dept)
    else:
        print(f'WARNING: {dept} not found in JSON')

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'\n✓ 已更新 {len(updated)} 個系所備注到 {OUTPUT}')
for dept in sorted(updated):
    print(f'  - {dept}')
