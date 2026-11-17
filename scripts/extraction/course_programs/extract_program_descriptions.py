"""
extract_program_descriptions.py

從 data/raw/學分學程/ 下所有 39 份 PDF 萃取學分學程的文字說明。
策略：用 pdfplumber find_tables() 取得課程表格 bbox，過濾掉表格區域後
      再用 extract_text() 取純文字，只保留從「一、」開始的條款內容。

輸出：data/processed/program_descriptions.json
格式：
{
  "「氣候與環境變遷」學分學程": {
    "college": "地科學院",
    "description": "一、本學程之目的...",
    "source": "pdfplumber"
  },
  ...
}
"""

import pdfplumber
import re
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'data' / 'raw' / '學分學程'
OUTPUT = ROOT / 'data' / 'processed' / 'program_descriptions.json'


def extract_text_no_tables(pdf_path: Path) -> str:
    """提取 PDF 全頁文字，跳過 pdfplumber 偵測到的表格區域。"""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            if not tables:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
            else:
                table_bboxes = [tbl.bbox for tbl in tables]

                def not_in_any_table(obj):
                    x0, top, x1, bottom = obj['x0'], obj['top'], obj['x1'], obj['bottom']
                    for tb in table_bboxes:
                        if x0 >= tb[0] - 2 and x1 <= tb[2] + 2 and \
                           top >= tb[1] - 2 and bottom <= tb[3] + 2:
                            return False
                    return True

                filtered = page.filter(not_in_any_table)
                t = filtered.extract_text()
                if t:
                    pages_text.append(t)
    return '\n'.join(pages_text)


def clean_description(text: str) -> str:
    """
    1. 去除版本歷程（開頭到第一個「一、」之前）。
    2. 合併被斷行的連續中文段落（非標號行合併到上一行）。
    3. 去除空行與頁碼行。
    """
    # 找第一個「一、」的位置
    m = re.search(r'[一㇐]\s*[、，。\s]', text)
    if m:
        text = text[m.start():]

    _ITEM_RE = re.compile(
        r'^(?:'
        r'[一二三四五六七八九十㇐]\s*[、，。\s]'  # 一、 二、
        r'|\(\s*[一二三四五六七八九十㇐]\s*[）)]\s*'  # (一)
        r'|\(\s*\d+\s*[）)]\s*'               # (1) (二)
        r'|\d+\s*[、．.]\s*'                   # 1. 2.
        r')'
    )

    result_lines = []
    for raw_line in text.split('\n'):
        stripped = raw_line.strip()
        if not stripped:
            continue
        # 去頁碼行
        if re.fullmatch(r'\d+', stripped):
            continue
        if re.match(r'^\d+-\d+', stripped):
            continue

        if not result_lines or _ITEM_RE.match(stripped):
            result_lines.append(stripped)
        else:
            # 非標號行：合併到上一行
            # 若上一行以中文字結尾且本行以中文開頭 → 直接接（補斷行）
            prev = result_lines[-1]
            if prev and re.search(r'[\u4e00-\u9fff，。：；、）」』]$', prev) and \
               re.match(r'^[\u4e00-\u9fff（「『]', stripped):
                result_lines[-1] += stripped
            else:
                result_lines[-1] += ' ' + stripped

    return '\n'.join(result_lines)


def normalize_program_name(stem: str) -> str:
    """去除書名號以外的括號前綴，標準化學程名稱。"""
    # 例：「氣候與環境變遷」學分學程 → 直接保留
    return stem.strip()


# ─── 主流程 ──────────────────────────────────────────────────

results = {}

for pdf_path in sorted(BASE.rglob('*.pdf')):
    college = pdf_path.parent.name
    program_name = normalize_program_name(pdf_path.stem)

    try:
        raw_text = extract_text_no_tables(pdf_path)
        description = clean_description(raw_text)
        results[program_name] = {
            'college': college,
            'description': description,
            'source': 'pdfplumber',
        }
        print(f'[OK] {program_name[:30]:<30}  ({len(description)} chars)')
    except Exception as e:
        print(f'[ERR] {program_name}: {e}')
        results[program_name] = {
            'college': college,
            'description': '',
            'source': 'error',
        }

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f'\n✓ 共萃取 {len(results)} 個學程，已寫入 {OUTPUT}')

# ─── 預覽 ────────────────────────────────────────────────────

print('\n── 預覽（前 3 個）──')
for name, entry in list(results.items())[:3]:
    print(f'\n[{name}]')
    print(entry['description'][:300].replace('\n', ' | '))
