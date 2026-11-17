"""
deduplicate_courses.py — 建立正規化課程 canonical JSON

去重規則：
  Key = 課號-班別（完整字串，含班別後綴，如 CE1001-A、CE1001-B、CE1001-*）
  同一 Key 出現多次時，優先順序（高者蓋低者）：
    scraped_missing（最低）→ 114_1 → 114_2（最高）

scraped_missing 處理：
  courses.json 混有學士與研究所課程，依系所名稱對照
  graduate_courses 目錄的檔名進行拆分，各自注入對應 pipeline。

輸出（保持 raw 欄位格式，與 courses.py convert_course_format 相容）：
  data/processed/courses_deduped/undergrad.json
  data/processed/courses_deduped/grad.json

用法：
  python scripts/rag/deduplicate_courses.py
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
RAW  = ROOT / "data" / "raw"
OUT  = ROOT / "data" / "processed" / "courses_deduped"

# 學期清單（舊→新，後者蓋前者）。可用環境變數 NCU_DATA_TERMS 覆寫，例如 "115_1,115_2"；
# 資料更新管線（python -m scripts.update_data --terms ...）會自動帶入。
TERMS = [t.strip() for t in os.environ.get("NCU_DATA_TERMS", "114_1,114_2").split(",") if t.strip()]

DEPT_COLLEGE_MAP_PATH = ROOT / "data" / "processed" / "dept_college_map.json"


def load_dept_college_map() -> dict[str, str]:
    if not DEPT_COLLEGE_MAP_PATH.exists():
        print(f"  [WARN] dept_college_map.json 不存在，跳過學院補齊")
        return {}
    return json.loads(DEPT_COLLEGE_MAP_PATH.read_text(encoding="utf-8"))


def fill_missing_college(courses: list[dict], dept_college_map: dict[str, str]) -> int:
    """對缺少「學院」欄位的課程，依「系所」查 map 補齊。回傳補齊筆數。"""
    filled = 0
    for c in courses:
        if not c.get("學院"):
            dept = c.get("系所", "")
            college = dept_college_map.get(dept, "")
            if college:
                c["學院"] = college
                filled += 1
    return filled


def build_grad_depts() -> set[str]:
    """從 graduate_courses 目錄的檔名抽出研究所系所名稱集合。
    檔名格式：學院_系所.json，取底線後半段作為系所名稱。
    """
    grad_depts: set[str] = set()
    for semester in TERMS:
        d = RAW / "graduate_courses" / semester
        if d.exists():
            for f in d.glob("*.json"):
                dept = f.stem.split("_", 1)[-1] if "_" in f.stem else f.stem
                grad_depts.add(dept)
    return grad_depts


def split_scraped_missing(grad_depts: set[str]) -> tuple[list[dict], list[dict]]:
    """載入 scraped_missing/courses.json，依系所拆分為（學士, 研究所）。"""
    sm_path = RAW / "scraped_missing" / "courses.json"
    if not sm_path.exists():
        print(f"  [SKIP] scraped_missing: {sm_path} 不存在")
        return [], []
    all_courses = json.loads(sm_path.read_text(encoding="utf-8"))
    if not isinstance(all_courses, list):
        return [], []
    ug, grad = [], []
    for c in all_courses:
        if c.get("系所", "") in grad_depts:
            grad.append(c)
        else:
            ug.append(c)
    print(f"  [scraped_missing] 拆分：學士 {len(ug)} 筆 / 研究所 {len(grad)} 筆")
    return ug, grad


def load_from_dir(dir_path: Path) -> list[dict]:
    courses = []
    for fp in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                courses.extend(data)
        except Exception as e:
            print(f"  [WARN] {fp.name}: {e}")
    return courses


def deduplicate(sources: list[tuple[str, "Path | list[dict]"]]) -> list[dict]:
    """依 sources 順序載入並去重（後者覆蓋前者），key = 課號-班別。
    第二個元素可以是 Path（從檔案/目錄載入）或 list（直接使用）。
    """
    seen: dict[str, dict] = {}
    for label, path_or_list in sources:
        if isinstance(path_or_list, list):
            courses = path_or_list
        elif not path_or_list.exists():
            print(f"  [SKIP] {label}: {path_or_list} 不存在")
            continue
        elif path_or_list.is_file():
            data = json.loads(path_or_list.read_text(encoding="utf-8"))
            courses = data if isinstance(data, list) else []
        else:
            courses = load_from_dir(path_or_list)

        before = len(seen)
        for c in courses:
            key = c.get("課號-班別", "").strip()
            if key:
                seen[key] = c
        print(f"  [{label}] 載入 {len(courses)} 筆，累計 unique: {len(seen)}（新增 {len(seen)-before}）")

    return list(seen.values())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dept_college_map = load_dept_college_map()
    print(f"  [dept_college_map] 載入 {len(dept_college_map)} 筆系所→學院對應\n")

    grad_depts = build_grad_depts()
    print(f"  [grad_depts] 從 graduate_courses 目錄識別 {len(grad_depts)} 個研究所系所\n")

    sm_ug, sm_grad = split_scraped_missing(grad_depts)
    print()

    undergrad_sources: list[tuple[str, "Path | list[dict]"]] = [
        ("scraped_missing(學士)", sm_ug),
        *[(term, RAW / "courses" / term) for term in TERMS],
    ]

    grad_sources: list[tuple[str, "Path | list[dict]"]] = [
        ("scraped_missing(研究所)", sm_grad),
        *[(term, RAW / "graduate_courses" / term) for term in TERMS],
    ]

    print("=== 大學部課程去重 ===")
    undergrad = deduplicate(undergrad_sources)
    filled = fill_missing_college(undergrad, dept_college_map)
    print(f"  [補齊學院] {filled} 筆（原本缺少「學院」欄位）")
    before = len(undergrad)
    undergrad = [c for c in undergrad if c.get("系所", "").strip()]
    removed = before - len(undergrad)
    if removed:
        print(f"  [移除] {removed} 筆（系所為空的不完整資料）")
    ug_path = OUT / "undergrad.json"
    ug_path.write_text(json.dumps(undergrad, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 輸出 {len(undergrad)} 筆 → {ug_path}\n")

    print("=== 研究所課程去重 ===")
    grad = deduplicate(grad_sources)
    filled_g = fill_missing_college(grad, dept_college_map)
    print(f"  [補齊學院] {filled_g} 筆（原本缺少「學院」欄位）")
    before_g = len(grad)
    grad = [c for c in grad if c.get("系所", "").strip()]
    removed_g = before_g - len(grad)
    if removed_g:
        print(f"  [移除] {removed_g} 筆（系所為空的不完整資料）")
    grad_path = OUT / "grad.json"
    grad_path.write_text(json.dumps(grad, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 輸出 {len(grad)} 筆 → {grad_path}")

    # 簡單驗證：確認同課號-班別不重複
    ug_keys = [c.get("課號-班別", "") for c in undergrad]
    dups = len(ug_keys) - len(set(ug_keys))
    print(f"\n[驗證] undergrad 重複 key 數：{dups}（應為 0）")
    grad_keys = [c.get("課號-班別", "") for c in grad]
    dups_g = len(grad_keys) - len(set(grad_keys))
    print(f"[驗證] grad 重複 key 數：{dups_g}（應為 0）")


if __name__ == "__main__":
    main()
