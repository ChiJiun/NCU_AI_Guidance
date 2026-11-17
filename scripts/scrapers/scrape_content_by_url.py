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
# 斷點續爬：每個學期目錄裡放一個斷點檔（不是 .json，不會被當成系所檔讀進去），
# 記錄已處理的課程鍵（檔名 + 課號-班別 + 學期）。重新爬課程時整個學期目錄會被換掉，
# 斷點也跟著清空，重爬後課綱空白的課會重新補齊。
# 舊版的 data/raw/scraped_missing/content_fix_checkpoint.json 不再讀取。
CHECKPOINT_NAME = '.content_fix_done.txt'
# 「補課綱未完成」標記：資料更新管線把新爬的課程換進學期目錄時寫入，這支腳本成功跑完
# （結束碼 0、不是 dry-run、沒有用 --limit 截斷）才刪除；標記存在時管線不會用這些課程 build。
# 檔名必須與 scripts/update_data/fetch.py 的 CONTENT_PENDING_NAME 相同。
PENDING_MARKER_NAME = '.content_fix_pending'

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


# 課程綱要頁一定會有的識別欄位；一個都沒解析到，就當成錯誤頁
OUTLINE_IDENTITY_FIELDS = ('課號', '流水號', '課程名稱(中文)')


def is_outline_page(outline: dict) -> bool:
    return any(str(outline.get(f) or '').strip() for f in OUTLINE_IDENTITY_FIELDS)


# ─── 爬取單筆課程 ─────────────────────────────────────────────────────────────

def scrape_course(driver, course: dict, dry_run: bool) -> tuple[bool, bool]:
    """
    爬取 course 的課程綱要（與分發條件若也空白）。
    回傳 (updated, error)：updated 表示有補到資料；error 表示途中有頁面載入或解析失敗，
    這門課不能記進斷點（下次要重試）。
    dry_run=True 時只解析但不寫回。
    """
    綱要_url = course.get('課程綱要_連結', '')
    分發_url = course.get('分發條件_連結', '')
    if '課程綱要' not in course or course['課程綱要'] is None:
        course['課程綱要'] = {}
    existing_綱要 = course['課程綱要']

    updated = False
    error = False

    # ── 課程綱要 ──
    if 綱要_url:
        try:
            driver.get(綱要_url)
            time.sleep(1.5)
            outline = parse_outline_page(driver)
            if outline.get('_parse_error'):
                error = True
                print(f"    [綱要解析錯誤] {str(outline['_parse_error'])[:60]}")
            elif not is_outline_page(outline):
                # 頁面載入了但不是課程綱要（例如「系統忙碌」錯誤頁）：不能當成「無新資料」記進斷點
                error = True
                outline = {}
                print('    [綱要頁異常] 找不到課號／流水號／課程名稱，可能是錯誤頁')

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
            error = True
            print(f'    [綱要錯誤] {str(e)[:60]}')

    # ── 分發條件（只在空白時補）──
    existing_分發 = course.get('分發條件') or {}
    has_分發 = bool(existing_分發.get('優先順序列表') or existing_分發.get('限制說明'))
    if 分發_url and not has_分發:
        try:
            driver.get(分發_url)
            time.sleep(1.2)
            condition = parse_condition_page(driver)
            if condition.get('_parse_error'):
                error = True
                print(f"    [分發解析錯誤] {str(condition['_parse_error'])[:60]}")
            else:
                if condition and not dry_run:
                    course['分發條件'] = condition
                if condition:
                    updated = True
        except Exception as e:
            error = True
            print(f'    [分發錯誤] {str(e)[:60]}')

    return updated, error


# ─── 收集所有待爬課程（file_path, index）─────────────────────────────────────

def collect_targets(dirs=None) -> list[tuple[Path, int]]:
    """回傳 [(file_path, course_index), ...]，只收集目標+內容皆空的課程"""
    targets = []
    for d in (COURSE_DIRS if dirs is None else dirs):
        for f in sorted(d.glob('*.json')):
            data = json.loads(f.read_text(encoding='utf-8'))
            for i, course in enumerate(data):
                if needs_update(course) and course.get('課程綱要_連結'):
                    targets.append((f, i))
    return targets


# ─── 斷點續爬 ─────────────────────────────────────────────────────────────────

def checkpoint_key(file_path: Path, course: dict) -> str:
    """斷點鍵：'檔名::課號-班別::學年度學期'（斷點檔放在該學期目錄裡）。"""
    ident = course.get('課號-班別') or course.get('流水號') or ''
    term = f"{course.get('學年度', '')}{course.get('學期', '')}"
    return f'{file_path.name}::{ident}::{term}'


def checkpoint_path(course_dir: Path) -> Path:
    return course_dir / CHECKPOINT_NAME


def load_checkpoint(course_dir: Path) -> set[str]:
    """回傳該學期目錄已完成的 key 集合，格式見 checkpoint_key()"""
    p = checkpoint_path(course_dir)
    if p.is_file():
        return {line for line in p.read_text(encoding='utf-8').splitlines() if line.strip()}
    return set()


def save_checkpoint(course_dir: Path, done: set[str]):
    if not course_dir.is_dir():
        return
    p = checkpoint_path(course_dir)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(''.join(f'{k}\n' for k in sorted(done)), encoding='utf-8')
    os.replace(tmp, p)


def clear_pending_markers(dirs=None) -> list[Path]:
    """刪除各學期目錄的「補課綱未完成」標記，回傳實際刪掉的檔案。"""
    removed = []
    for d in (COURSE_DIRS if dirs is None else dirs):
        marker = d / PENDING_MARKER_NAME
        if marker.is_file():
            marker.unlink()
            removed.append(marker)
    return removed


def pending_targets(dirs=None) -> tuple[list[tuple[Path, int]], dict[Path, set[str]]]:
    """回傳 (待爬清單, {學期目錄: 已完成鍵})；已記進斷點的課程不列入待爬。"""
    dirs = COURSE_DIRS if dirs is None else dirs
    done_by_dir = {d: load_checkpoint(d) for d in dirs}
    pending = []
    cache: dict[Path, list] = {}
    for f, i in collect_targets(dirs):
        if f not in cache:
            cache[f] = json.loads(f.read_text(encoding='utf-8'))
        if checkpoint_key(f, cache[f][i]) not in done_by_dir.get(f.parent, set()):
            pending.append((f, i))
    return pending, done_by_dir


class ErrorBudget:
    """錯誤預算：連續出錯太多（通常是瀏覽器掛掉或網站擋人）就提早中止，
    跑完後錯誤率太高也視為失敗，讓資料更新管線停在 fetch 階段、不往下 build。"""

    def __init__(self, max_consecutive: int = 10, max_rate: float = 0.2):
        self.max_consecutive, self.max_rate = max_consecutive, max_rate
        self.streak = 0
        self.processed = 0
        self.errors = 0

    def record(self, error: bool) -> None:
        self.processed += 1
        if error:
            self.errors += 1
            self.streak += 1
        else:
            self.streak = 0

    @property
    def exhausted(self) -> bool:
        """連續錯誤達上限，應立即中止。"""
        return self.max_consecutive > 0 and self.streak >= self.max_consecutive

    def failed(self) -> bool:
        """整體是否算失敗：提早中止、或錯誤率超過上限。"""
        if self.exhausted:
            return True
        return self.processed > 0 and self.errors / self.processed > self.max_rate


def process_file(driver, file_path: Path, indices: list[int], done: set[str], *,
                 dry_run: bool, scrape=None, pause: float = 0.8,
                 start: int = 0, total: int = 0, budget: ErrorBudget | None = None) -> dict[str, int]:
    """處理同一個檔案裡的待爬課程，回傳 {'processed', 'updated', 'errors'}。

    只有沒發生錯誤、且不是 dry-run 的課程才會加進 done（出錯的下次重試）。
    budget 連續錯誤達上限時停止處理剩下的課（已補到的資料仍會寫回）。
    有更新時以暫存檔＋os.replace 寫回，避免中斷留下半個 JSON。
    """
    scrape = scrape or scrape_course
    data = json.loads(file_path.read_text(encoding='utf-8'))
    counts = {'processed': 0, 'updated': 0, 'errors': 0}

    for i in indices:
        if budget is not None and budget.exhausted:
            break
        course = data[i]
        name = course.get('課程名稱(中文)', '')
        dept = course.get('系所', '')
        print(f'[{start + counts["processed"] + 1}/{total}] {dept} | {name}', end=' ... ')

        try:
            updated, error = scrape(driver, course, dry_run=dry_run)
        except Exception as e:
            updated, error = False, True
            print(f'❌ {str(e)[:50]}', end=' ')
        if updated:
            counts['updated'] += 1
        if error:
            counts['errors'] += 1
            print('⚠ 有錯誤，下次重試' + ('（已補到部分資料）' if updated else ''))
        else:
            print('✅ 補齊' if updated else '– 無新資料')
            # dry-run 不記斷點，否則之後正式跑會跳過這些課程
            if not dry_run:
                done.add(checkpoint_key(file_path, course))
        counts['processed'] += 1
        if budget is not None:
            budget.record(error)
        if pause:
            time.sleep(pause)

    if counts['updated'] > 0 and not dry_run:
        tmp = file_path.with_name(file_path.name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, file_path)
        print(f'  → 已儲存 {file_path.name}（更新 {counts["updated"]} 門課）')
    return counts


# ─── 主程式 ──────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    """回傳結束碼：0 成功；1 連續錯誤過多而中止、或錯誤率超過上限。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true', help='無頭模式')
    parser.add_argument('--limit', type=int, default=0, help='最多處理幾筆（0=全部）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只解析，不寫回檔案（測試用）')
    parser.add_argument('--max-consecutive-errors', type=int, default=10,
                        help='連續幾筆出錯就中止並以結束碼 1 結束（0=不限）；預設 10')
    parser.add_argument('--max-error-rate', type=float, default=0.2,
                        help='錯誤筆數佔已處理筆數超過此比例就以結束碼 1 結束；預設 0.2')
    args = parser.parse_args(argv)

    print('掃描待補課程...')
    targets = collect_targets()
    print(f'找到 {len(targets)} 筆待補課程（目標+內容皆空且有連結）')

    pending, done_by_dir = pending_targets()
    print(f'已完成 {sum(len(v) for v in done_by_dir.values())} 筆，待爬 {len(pending)} 筆')

    truncated = bool(args.limit) and len(pending) > args.limit
    if args.limit:
        pending = pending[:args.limit]
        print(f'（限制 {args.limit} 筆）')

    def finish_ok() -> int:
        # 全部待補課程都處理過才算補完；dry-run 不改任何檔案
        if not args.dry_run and not truncated:
            for marker in clear_pending_markers():
                print(f'補課綱已完成，移除標記 {marker}')
        return 0

    if not pending:
        print('無待處理項目，結束。')
        return finish_ok()

    driver = make_driver(headless=args.headless)

    # 按檔案分組，避免同一檔案多次讀寫
    from collections import defaultdict
    file_groups: dict[Path, list[int]] = defaultdict(list)
    for f, i in pending:
        file_groups[f].append(i)

    budget = ErrorBudget(args.max_consecutive_errors, args.max_error_rate)
    totals = {'processed': 0, 'updated': 0, 'errors': 0}
    try:
        for file_path, indices in file_groups.items():
            counts = process_file(driver, file_path, indices, done_by_dir[file_path.parent],
                                  dry_run=args.dry_run, start=totals['processed'], total=len(pending),
                                  budget=budget)
            for k in totals:
                totals[k] += counts[k]
            # 每個檔案處理完存一次斷點
            if not args.dry_run:
                save_checkpoint(file_path.parent, done_by_dir[file_path.parent])
            if budget.exhausted:
                print(f'\n連續 {budget.streak} 筆出錯，可能是瀏覽器掛掉或網站暫時無法連線，中止。')
                break
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        if not args.dry_run:
            for d, done in done_by_dir.items():
                save_checkpoint(d, done)
        prefix = '[DRY-RUN] ' if args.dry_run else ''
        print(f"\n{prefix}完成：處理 {totals['processed']}／{len(pending)} 筆，實際補齊 {totals['updated']} 筆，"
              f"錯誤 {totals['errors']} 筆")
        if args.dry_run:
            print('（dry-run 模式，未寫回，去掉 --dry-run 重跑）')
        else:
            print(f'斷點記錄：各學期目錄下的 {CHECKPOINT_NAME}（重新爬課程時會隨目錄一起換掉）')
            print('重新跑可繼續未完成的部分（出錯的課程會重試）。若想從頭跑，刪除斷點檔即可。')

    if budget.failed():
        reason = (f'連續 {budget.streak} 筆出錯而中止' if budget.exhausted
                  else f'錯誤率 {budget.errors}/{budget.processed} 超過 {budget.max_rate:.0%}')
        print(f'補課綱失敗：{reason}。以結束碼 1 結束，資料更新管線不會往下 build；修好後重跑會從斷點續爬。')
        return 1
    return finish_ok()


if __name__ == '__main__':
    raise SystemExit(main())
