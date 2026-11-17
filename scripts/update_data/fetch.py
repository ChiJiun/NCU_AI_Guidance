"""課程爬取：先爬到暫存目錄（可續爬），筆數驗證通過才換進 data/raw。

v2 爬蟲會把全校（含碩博士）系所都存進同一個目錄；下游 deduplicate_courses 依
data/raw/graduate_courses/<學期>/ 的檔名判斷研究所，所以這裡負責自動分流
（以前這一步是手動搬檔）。
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GRAD_NAME_RE = re.compile(r"碩士|博士|研究所|研究學院|在職|專班|學位學程")
TERM_RE = re.compile(r"^(\d{3})_([12])$")

SCRAPER = "scripts/scrapers/ncu_course_scraper_v2.py"


def parse_term(term: str) -> tuple[str, str]:
    m = TERM_RE.match(term)
    if not m:
        raise ValueError(f"學期格式應為 <學年>_<1|2>，例如 114_1，收到 {term!r}")
    return m.group(1), m.group(2)


def dept_of(stem: str) -> str:
    """檔名 <學院>_<系所>.json → 系所。"""
    return stem.split("_", 1)[1] if "_" in stem else stem


def known_dept_levels(root: Path) -> tuple[set[str], set[str]]:
    """從現有資料推得的（大學部系所, 研究所系所）。"""
    ug: set[str] = set()
    grad: set[str] = set()
    for level, bucket in (("undergrad", ug), ("grad", grad)):
        p = root / "data" / "processed" / "courses_deduped" / f"{level}.json"
        if p.is_file():
            try:
                bucket.update(c.get("系所", "") for c in json.loads(p.read_text(encoding="utf-8"))
                              if isinstance(c, dict) and c.get("系所"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
    gdir = root / "data" / "raw" / "graduate_courses"
    if gdir.is_dir():
        grad.update(dept_of(f.stem) for f in gdir.glob("*/*.json"))
    return ug, grad


def classify_dept_file(stem: str, ug_depts: set[str], grad_depts: set[str]) -> str:
    """回傳 "graduate_courses" 或 "courses"。已知名單優先，其次看名稱。"""
    dept = dept_of(stem)
    in_ug, in_grad = dept in ug_depts, dept in grad_depts
    if in_grad and not in_ug:
        return "graduate_courses"
    if in_ug and not in_grad:
        return "courses"
    # 「學士學位學程」「學士班」等是大學部，名稱也可能含「學位學程」，先排除
    if "學士" in dept:
        return "courses"
    return "graduate_courses" if GRAD_NAME_RE.search(dept) else "courses"


def count_courses(dirs: list[Path]) -> tuple[int, int]:
    """（檔案數, 課程數）；讀不了的檔案不計入課程數。"""
    files = courses = 0
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            files += 1
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                courses += len(data) if isinstance(data, list) else 0
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
    return files, courses


@dataclass
class TermResult:
    term: str
    ok: bool
    detail: str
    files: int = 0
    courses: int = 0
    old_courses: int = 0


def check_term(staging: Path, root: Path, term: str, max_shrink: float, allow_shrink: bool) -> TermResult:
    files, courses = count_courses([staging])
    _, old = count_courses([root / "data" / "raw" / "courses" / term,
                            root / "data" / "raw" / "graduate_courses" / term])
    if files == 0 or courses == 0:
        return TermResult(term, False, "暫存目錄沒有任何課程，可能是頁面改版或連線失敗", files, courses, old)
    if not allow_shrink and old and courses < old * (1 - max_shrink):
        return TermResult(term, False, f"課程數 {courses} 比現有 {old} 少超過 {max_shrink:.0%}，"
                                       f"可能沒爬完（重跑會從暫存目錄續爬）", files, courses, old)
    return TermResult(term, True, f"{files} 個系所檔、{courses} 門課（現有 {old} 門）", files, courses, old)


def promote_term(staging: Path, root: Path, term: str, backup_dir: Path,
                 ug_depts: set[str], grad_depts: set[str]) -> dict[str, int]:
    """把暫存目錄分流後換進 data/raw/{courses,graduate_courses}/<term>；舊目錄移到 backup_dir。

    整個學期目錄被換掉，舊目錄裡的補課綱斷點（scrape_content_by_url 的 .content_fix_done.txt）
    也一起移走，所以重爬後課綱空白的課會重新補齊。只複製 *.json，不會帶入暫存檔或斷點。
    """
    split_root = staging.parent / f"{term}.split"
    if split_root.exists():
        shutil.rmtree(split_root)
    counts = {"courses": 0, "graduate_courses": 0}
    for f in sorted(staging.glob("*.json")):
        level = classify_dept_file(f.stem, ug_depts, grad_depts)
        dst = split_root / level / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        counts[level] += 1

    for level in ("courses", "graduate_courses"):
        target = root / "data" / "raw" / level / term
        if target.exists():
            dest = backup_dir / "raw" / level / term
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(dest))
        src = split_root / level
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.move(str(src), str(target))
        else:
            target.mkdir(parents=True, exist_ok=True)

    # 暫存目錄已完整複製進 data/raw，移進本次 run 目錄留存（不刪除）
    done = backup_dir / "incoming_done" / term
    done.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staging), str(done))
    shutil.rmtree(split_root, ignore_errors=True)
    return counts


def fetch_courses(*, root: Path, run_dir: Path, terms: list[str], python: str,
                  run: Callable[[list[str]], int], log: Callable[[str], None],
                  max_shrink: float, allow_shrink: bool, fresh: bool) -> tuple[bool, str]:
    """爬取所有學期；全部驗證通過才一起換進 data/raw。"""
    incoming = root / "logs" / "data_update" / "incoming"
    results: list[TermResult] = []
    for term in terms:
        year, sem = parse_term(term)
        staging = incoming / term
        if fresh and staging.exists():
            stale = run_dir / "stale_incoming" / term
            stale.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging), str(stale))
            log(f"[{term}] --fresh-fetch：舊暫存目錄移到 {stale}")
        if staging.exists():
            n, _ = count_courses([staging])
            log(f"[{term}] 從暫存目錄續爬（已有 {n} 個系所檔）：{staging}")
        staging.mkdir(parents=True, exist_ok=True)

        rc = run([python, SCRAPER, "--year", year, "--semesters", sem,
                  "--output-dir", str(staging), "--headless"])
        if rc != 0:
            return False, f"{term} 爬蟲結束碼 {rc}；已爬的系所留在 {staging}，重跑會續爬"
        res = check_term(staging, root, term, max_shrink, allow_shrink)
        log(f"[{term}] {res.detail}")
        if not res.ok:
            return False, f"{term}：{res.detail}"
        results.append(res)

    ug, grad = known_dept_levels(root)
    summary = []
    for res in results:
        counts = promote_term(incoming / res.term, root, res.term, run_dir, ug, grad)
        summary.append(f"{res.term}：大學部 {counts['courses']} 檔、研究所 {counts['graduate_courses']} 檔，"
                       f"{res.courses} 門課（原 {res.old_courses}）")
    return True, "；".join(summary)
