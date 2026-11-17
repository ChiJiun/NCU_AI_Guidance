"""
直接使用課程 JSON 中已存在的「課程綱要_連結」和「分發條件_連結」，
補齊 raw/courses 和 raw/graduate_courses 中缺少課程目標 + 授課內容的課程。

優點：
  - 不需搜尋課號、不需選學期，直接導向正確學期的頁面
  - 每筆課程獨立爬取，班別之間互不干擾
  - 支援斷點續爬（進度存在 checkpoint JSON）
  - 只補空白欄位，不覆蓋已有資料

使用方式：
  python scripts/scrapers/scrape_content_by_url.py [--headless] [--limit N] [--dry-run]

輸出：直接更新原始 JSON 檔案（in-place）
"""

import json
import os
import re
import time
import argparse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

BASE = Path(__file__).parent.parent.parent
# 學期清單可用環境變數 NCU_DATA_TERMS 覆寫（例如 "115_1,115_2"），資料更新管線會自動帶入
TERMS = [t.strip() for t in os.environ.get('NCU_DATA_TERMS', '114_1,114_2').split(',') if t.strip()]
COURSE_DIRS = [BASE / 'data' / 'raw' / level / term
               for level in ('courses', 'graduate_courses') for term in TERMS]
# 斷點續爬：記錄已處理的課程鍵（檔案 + 課號-班別 + 學期，不用索引，重爬後索引會變）
CHECKPOINT_PATH = BASE / 'data' / 'raw' / 'scraped_missing' / 'content_fix_checkpoint.json'

SYLLABUS_FIELDS = [
    '課程目標', '授課內容', '課程領域', '授課方式',
    '評量配分比重', '教科書/參考書', '授課週數',
]


# ─── 判斷欄位是否有值 ─────────────────────────────────────────────────────────

def has_content(val) -> bool:
    return len(str(val or '').strip()) >= 10


def needs_update(course: dict) -> bool:
    """目標+內容皆空才需要爬"""
    綱要 = course.get('課程綱要') or {}
    obj  = str(綱要.get('課程目標', '') or '').strip()
    cont = str(綱要.get('授課內容', '') or '').strip()
    return len(obj) < 10 and len(cont) < 10


# ─── Selenium ────────────────────────────────────────────────────────────────

def make_driver(headless: bool = False) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--start-maximized')
    return webdriver.Chrome(options=opts)


# ─── 解析課程綱要頁面 ──────────────────────────────────────────────────────────

def parse_outline_page(driver) -> dict:
    """解析課程綱要彈出視窗（直接導向 URL 後解析）"""
    result = {}
    try:
        # 核心能力表格
        core_abilities = []
        try:
            tbl = driver.find_element(
                By.XPATH, "//th[normalize-space()='系所核心能力']/ancestor::table[1]")
            for row in tbl.find_elements(By.TAG_NAME, 'tr')[1:]:
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) >= 3 and cells[0].text.strip():
                    core_abilities.append({
                        '能力名稱': cells[0].text.strip(),
                        '強度指數': cells[1].text.strip(),
                        '評量方式': cells[2].text.strip(),
                    })
        except Exception:
            pass

        # 主體文字 → 逐行解析欄位
        text = driver.find_element(By.TAG_NAME, 'body').text
        field_keywords = [
            '學期', '開課單位', '流水號', '課號', '授課教師',
            '課程名稱(中文)', '課程名稱(英文)', '課程學制', '學分',
            '課程目標', '授課內容', '教科書/參考書', '自編教材比例',
            '授課方式', '評量配分比重', '辦公時間', '授課週數',
            '彈性教學說明', '課程領域', 'Office Hours', '備註',
        ]
        current_field, current_value = None, []
        for line in text.split('\n'):
            line = line.strip()
            if not line or '智慧財產權' in line:
                continue
            matched = False
            for kw in field_keywords:
                if line.startswith(kw + ' ') or line == kw:
                    if current_field and current_value:
                        result[current_field] = '\n'.join(current_value)
                    current_field = kw
                    val = line[len(kw):].strip()
                    current_value = [val] if val else []
                    matched = True
                    break
            if not matched and current_field:
                current_value.append(line)
        if current_field and current_value:
            result[current_field] = '\n'.join(current_value)

        # 清理課程領域（避免把核心能力表格文字也帶進來）
        if '課程領域' in result and '系所核心能力' in result['課程領域']:
            result['課程領域'] = result['課程領域'][:result['課程領域'].find('系所核心能力')].strip()

        result['核心能力'] = core_abilities
    except Exception as e:
        result['_parse_error'] = str(e)
    return result


# ─── 解析分發條件頁面 ──────────────────────────────────────────────────────────

def parse_condition_page(driver) -> dict:
    """解析分發條件彈出視窗（直接導向 URL 後解析）"""
    result = {}
    try:
        tables = driver.find_elements(By.TAG_NAME, 'table')
        for table in tables:
            rows = table.find_elements(By.TAG_NAME, 'tr')
            if len(rows) < 2:
                continue
            headers = [c.text.strip() for c in (
                rows[0].find_elements(By.TAG_NAME, 'th') or
                rows[0].find_elements(By.TAG_NAME, 'td')
            )]
            if any('優先' in h for h in headers):
                priorities = []
                for row in rows[1:]:
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) >= 2:
                        priorities.append({
                            '優先順序': cells[0].text.strip(),
                            '相關條件限制說明': cells[1].text.strip(),
                        })
                if priorities:
                    result['優先順序列表'] = priorities
        if not result:
            for cell in driver.find_elements(By.XPATH, "//td[@colspan='2']"):
                t = cell.text.strip()
                if t:
                    result['限制說明'] = t
                    break
    except Exception as e:
        result['_parse_error'] = str(e)
    return result


# ─── 爬取單筆課程 ─────────────────────────────────────────────────────────────

def scrape_course(driver, course: dict, dry_run: bool) -> bool:
    """
    爬取 course 的課程綱要（與分發條件若也空白）。
    回傳 True 表示有更新。
    dry_run=True 時只解析但不寫回。
    """
    綱要_url = course.get('課程綱要_連結', '')
    分發_url = course.get('分發條件_連結', '')
    if '課程綱要' not in course or course['課程綱要'] is None:
        course['課程綱要'] = {}
    existing_綱要 = course['課程綱要']

    updated = False

    # ── 課程綱要 ──
    if 綱要_url:
        try:
            driver.get(綱要_url)
            time.sleep(1.5)
            outline = parse_outline_page(driver)

            # 補回文字欄位
            for field in SYLLABUS_FIELDS:
                if not has_content(existing_綱要.get(field)) and has_content(outline.get(field)):
                    if not dry_run:
                        existing_綱要[field] = outline[field]
                    updated = True

            # 補回核心能力
            if not existing_綱要.get('核心能力') and outline.get('核心能力'):
                if not dry_run:
                    existing_綱要['核心能力'] = outline['核心能力']
                updated = True

        except Exception as e:
            print(f'    [綱要錯誤] {str(e)[:60]}')

    # ── 分發條件（只在空白時補）──
    existing_分發 = course.get('分發條件') or {}
    has_分發 = bool(existing_分發.get('優先順序列表') or existing_分發.get('限制說明'))
    if 分發_url and not has_分發:
        try:
            driver.get(分發_url)
            time.sleep(1.2)
            condition = parse_condition_page(driver)
            if condition and not dry_run:
                course['分發條件'] = condition
            if condition:
                updated = True
        except Exception as e:
            print(f'    [分發錯誤] {str(e)[:60]}')

    return updated


# ─── 收集所有待爬課程（file_path, index）─────────────────────────────────────

def collect_targets() -> list[tuple[Path, int]]:
    """回傳 [(file_path, course_index), ...]，只收集目標+內容皆空的課程"""
    targets = []
    for d in COURSE_DIRS:
        for f in sorted(d.glob('*.json')):
            data = json.loads(f.read_text(encoding='utf-8'))
            for i, course in enumerate(data):
                if needs_update(course) and course.get('課程綱要_連結'):
                    targets.append((f, i))
    return targets


# ─── 斷點續爬 ─────────────────────────────────────────────────────────────────

def checkpoint_key(file_path: Path, course: dict) -> str:
    """斷點鍵：'file_path::課號-班別::學年度學期'。"""
    ident = course.get('課號-班別') or course.get('流水號') or ''
    term = f"{course.get('學年度', '')}{course.get('學期', '')}"
    return f'{file_path}::{ident}::{term}'


def load_checkpoint() -> set[str]:
    """回傳已完成的 key 集合，格式見 checkpoint_key()"""
    if CHECKPOINT_PATH.exists():
        data = json.loads(CHECKPOINT_PATH.read_text(encoding='utf-8'))
        return set(data.get('done', []))
    return set()


def save_checkpoint(done: set[str]):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps({'done': sorted(done)}, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


# ─── 主程式 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true', help='無頭模式')
    parser.add_argument('--limit', type=int, default=0, help='最多處理幾筆（0=全部）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只解析，不寫回檔案（測試用）')
    args = parser.parse_args()

    # 收集目標
    print('掃描待補課程...')
    targets = collect_targets()
    print(f'找到 {len(targets)} 筆待補課程（目標+內容皆空且有連結）')

    # 載入斷點
    done_keys = load_checkpoint()
    _cache: dict[Path, list] = {}

    def _course_at(f: Path, i: int) -> dict:
        if f not in _cache:
            _cache[f] = json.loads(f.read_text(encoding='utf-8'))
        return _cache[f][i]

    pending = [(f, i) for f, i in targets
               if checkpoint_key(f, _course_at(f, i)) not in done_keys]
    _cache.clear()
    print(f'已完成 {len(done_keys)} 筆，待爬 {len(pending)} 筆')

    if args.limit:
        pending = pending[:args.limit]
        print(f'（限制 {args.limit} 筆）')

    if not pending:
        print('無待處理項目，結束。')
        return

    # 啟動 Selenium
    driver = make_driver(headless=args.headless)

    # 按檔案分組，避免同一檔案多次讀寫
    from collections import defaultdict
    file_groups: dict[Path, list[int]] = defaultdict(list)
    for f, i in pending:
        file_groups[f].append(i)

    total_updated = 0
    processed = 0

    try:
        for file_path, indices in file_groups.items():
            data = json.loads(file_path.read_text(encoding='utf-8'))
            file_updated = 0

            for i in indices:
                course = data[i]
                name = course.get('課程名稱(中文)', '')
                dept = course.get('系所', '')
                print(f'[{processed+1}/{len(pending)}] {dept} | {name}', end=' ... ')

                try:
                    updated = scrape_course(driver, course, dry_run=args.dry_run)
                    if updated:
                        file_updated += 1
                        total_updated += 1
                        print('✅ 補齊')
                    else:
                        print('– 無新資料')
                except Exception as e:
                    print(f'❌ {str(e)[:50]}')

                # dry-run 不記斷點，否則之後正式跑會跳過這些課程
                if not args.dry_run:
                    done_keys.add(checkpoint_key(file_path, course))
                processed += 1
                time.sleep(0.8)

            # 寫回檔案
            if file_updated > 0 and not args.dry_run:
                file_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                print(f'  → 已儲存 {file_path.name}（更新 {file_updated} 門課）')

            # 每個檔案處理完存一次斷點
            if not args.dry_run:
                save_checkpoint(done_keys)

    finally:
        driver.quit()
        if not args.dry_run:
            save_checkpoint(done_keys)
        prefix = '[DRY-RUN] ' if args.dry_run else ''
        print(f'\n{prefix}完成：處理 {processed} 筆，實際補齊 {total_updated} 筆')
        if args.dry_run:
            print('（dry-run 模式，未寫回，去掉 --dry-run 重跑）')
        else:
            print(f'斷點記錄：{CHECKPOINT_PATH}')
            print('重新跑可繼續未完成的部分。若想從頭跑，刪除上述斷點檔案即可。')


if __name__ == '__main__':
    main()
