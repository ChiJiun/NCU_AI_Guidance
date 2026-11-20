"""
validate_demos.py — 檢查展示版示範對話（frontend/public/demo/*.json）是否符合上線條件

檢查項目：
  - 每組示範的必要欄位、情境分類；每輪都有問題與回答
  - 個資：整輪紀錄（回答、推薦課程、分析步驟、來源）不可出現 email、手機、身分證字號格式，
    也不可殘留去識別化標記（例如 <PRIVATE_PERSON>）；研究助理示範不可出現該計畫學生姓名
  - 研究助理示範綁定的研究計畫要存在
  - 數量與涵蓋：課程 ≥ 10 組、研究 ≥ 3 組，四種情境分類（一般／複雜／資料不足／安全限制）都要出現
  - --require-reviewed：每組都必須已人工檢查（reviewed: true），部署前使用

用法：
  python scripts/demo/validate_demos.py
  python scripts/demo/validate_demos.py --require-reviewed   # 部署前
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "frontend" / "public" / "demo"
PROJECTS = ROOT / "data" / "processed" / "projects.json"

CATEGORIES = {"一般", "複雜", "資料不足", "安全限制"}
MIN_COURSE, MIN_RESEARCH = 10, 3

PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "手機號碼": re.compile(r"(?<!\d)09\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)"),
    "身分證字號": re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?!\d)"),
    "去識別化標記": re.compile(r"<\s*PRIVATE_[A-Z_]+\s*>"),
}


def iter_strings(value, path: str = "") -> list[tuple[str, str]]:
    """遞迴取出所有字串值（不含 dict key），回傳 (欄位路徑, 字串)。

    個資比對要逐個字串分開做：對 json.dumps 的結果跑 regex 會因為跳脫的換行漏判行首號碼，
    把字串串接起來又會讓手機 regex 跨欄位誤判。
    """
    if isinstance(value, str):
        return [(path or "$", value)]
    if isinstance(value, dict):
        return [item for k, v in value.items() for item in iter_strings(v, f"{path}.{k}" if path else str(k))]
    if isinstance(value, (list, tuple)):
        return [item for i, v in enumerate(value) for item in iter_strings(v, f"{path}[{i}]")]
    return []


def check_case(case: dict, assistant: str, *, projects: dict[str, dict], require_reviewed: bool) -> list[str]:
    errors: list[str] = []
    cid = case.get("id", "?")
    required = ["id", "title", "category", "summary", "turns", "reviewed", "recorded_at"]
    if assistant == "research":
        required.append("project_id")
    for key in required:
        if key not in case:
            errors.append(f"{cid}: 缺少欄位 {key}")
    if errors:
        return errors
    if case["category"] not in CATEGORIES:
        errors.append(f"{cid}: category={case['category']} 不合法")
    turns = case["turns"]
    if not turns:
        errors.append(f"{cid}: 沒有任何對話")
    for i, turn in enumerate(turns, 1):
        if not (turn.get("user") or "").strip():
            errors.append(f"{cid}: 第 {i} 輪沒有問題")
        if not (turn.get("assistant") or "").strip():
            errors.append(f"{cid}: 第 {i} 輪沒有回答")
        for field, text in iter_strings(turn):
            for label, pattern in PII_PATTERNS.items():
                if pattern.search(text):
                    errors.append(f"{cid}: 第 {i} 輪 {field} 疑似含 {label}，請人工確認")
    if assistant == "research":
        project = projects.get(case["project_id"])
        if project is None:
            errors.append(f"{cid}: 找不到研究計畫 {case['project_id']}")
        else:
            name = (project.get("studentName") or "").strip()
            if len(name) >= 2 and any(name in text for t in turns for _, text in iter_strings(t)):
                errors.append(f"{cid}: 對話紀錄中出現計畫學生姓名，請匿名化")
    if require_reviewed and case.get("reviewed") is not True:
        errors.append(f"{cid}: 尚未人工檢查（reviewed 不是 true）")
    return errors


def check_coverage(course: list[dict], research: list[dict]) -> list[str]:
    errors = []
    if len(course) < MIN_COURSE:
        errors.append(f"課程助理示範 {len(course)} < {MIN_COURSE}")
    if len(research) < MIN_RESEARCH:
        errors.append(f"研究助理示範 {len(research)} < {MIN_RESEARCH}")
    missing = CATEGORIES - {c.get("category") for c in course + research}
    if missing:
        errors.append(f"缺少情境分類：{sorted(missing)}")
    ids = [c.get("id") for c in course + research]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errors.append(f"示範 id 重複：{dup}")
    return errors


def load_cases(demo_dir: Path, name: str) -> list[dict]:
    path = demo_dir / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("cases", [])


def load_projects() -> dict[str, dict]:
    if not PROJECTS.exists():
        return {}
    return {p["id"]: p for p in json.loads(PROJECTS.read_text(encoding="utf-8"))}


def validate(demo_dir: Path, *, require_reviewed: bool) -> tuple[list[dict], list[dict], list[str]]:
    course = load_cases(demo_dir, "course-assistant.json")
    research = load_cases(demo_dir, "research-assistant.json")
    projects = load_projects()
    errors: list[str] = []
    for case in course:
        errors.extend(check_case(case, "course", projects=projects, require_reviewed=require_reviewed))
    for case in research:
        errors.extend(check_case(case, "research", projects=projects, require_reviewed=require_reviewed))
    errors.extend(check_coverage(course, research))
    return course, research, errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=DEMO_DIR)
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args()

    course, research, errors = validate(args.dir, require_reviewed=args.require_reviewed)
    reviewed = sum(1 for c in course + research if c.get("reviewed") is True)
    print(f"課程 {len(course)} 組、研究 {len(research)} 組，已人工檢查 {reviewed} 組")
    if errors:
        print("✗ 未通過：")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("✓ 通過")


if __name__ == "__main__":
    main()
