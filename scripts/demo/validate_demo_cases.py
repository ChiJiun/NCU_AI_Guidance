"""
validate_demo_cases.py — 檢查 frontend/src/demo/cases/ 的 Demo 案例是否符合比賽驗收條件

檢查項目：
  - 每個案例的必要欄位、助理類型、情境分類
  - 對話沒有錯誤、每輪都有回答
  - 內容完整性：重新計算 input + turns 的 sha256，必須與錄製時寫入的 meta.content_sha256 相同
    （人工檢查只能填 review 區塊，不能改 AI 回答；要修正請重錄）
  - 個資：整輪紀錄（回答、分析步驟、引用課程、來源）不可出現 email、手機、身分證字號格式；
    研究助理案例不可出現該計畫學生姓名
  - 數量與涵蓋：至少 13 組（課程 ≥10、研究 ≥3），六種情境分類都要出現
  - --require-approved：每個案例都必須已人工檢查（review.status == "approved" 且有 reviewer）

用法：
  python scripts/demo/validate_demo_cases.py
  python scripts/demo/validate_demo_cases.py --require-approved   # 比賽上線前
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = ROOT / "frontend" / "src" / "demo" / "cases"

ASSISTANTS = {"course", "research"}
CATEGORIES = {"general", "insufficient_data", "comparison", "anomaly", "safety", "complex"}
MIN_TOTAL, MIN_COURSE, MIN_RESEARCH = 13, 10, 3

PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "手機號碼": re.compile(r"(?<!\d)09\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)"),
    "身分證字號": re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?!\d)"),
}


def iter_strings(value, path: str = "") -> list[tuple[str, str]]:
    """遞迴取出所有字串值（不含 dict key），回傳 (欄位路徑, 字串)。

    個資比對要逐個字串分開做：
      - 不能對 json.dumps 的結果跑 regex：換行會變成反斜線加 n，身分證字號 regex 的
        lookbehind 會被前面的 `n` 擋住而漏判行首號碼。
      - 也不能把所有字串串接起來：手機 regex 允許中間有空白，會把兩個欄位接成一組號碼而誤判。
    """
    if isinstance(value, str):
        return [(path or "$", value)]
    if isinstance(value, dict):
        return [item for k, v in value.items() for item in iter_strings(v, f"{path}.{k}" if path else str(k))]
    if isinstance(value, (list, tuple)):
        return [item for i, v in enumerate(value) for item in iter_strings(v, f"{path}[{i}]")]
    return []


def content_digest(case: dict) -> str:
    """錄製內容（input + turns）的 sha256；review 與 meta 不納入，人工檢查可自由填寫。"""
    payload = json.dumps({"input": case.get("input"), "turns": case.get("turns")},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_case(case: dict, *, student_names: dict[str, str], require_approved: bool) -> list[str]:
    errors: list[str] = []
    cid = case.get("id", "?")
    for key in ("id", "assistant", "category", "title", "scenario", "input", "turns", "meta", "review"):
        if key not in case:
            errors.append(f"{cid}: 缺少欄位 {key}")
    if errors:
        return errors
    if case["assistant"] not in ASSISTANTS:
        errors.append(f"{cid}: assistant={case['assistant']} 不合法")
    if case["category"] not in CATEGORIES:
        errors.append(f"{cid}: category={case['category']} 不合法")
    turns = case["turns"]
    if not turns:
        errors.append(f"{cid}: 沒有任何對話")
    expected = (case.get("meta") or {}).get("content_sha256")
    if not expected:
        errors.append(f"{cid}: meta 缺少 content_sha256（請用 record_demo_cases.py 重錄）")
    elif expected != content_digest(case):
        errors.append(f"{cid}: 錄製內容與 content_sha256 不符，AI 回答或輸入可能被手動修改過，請重錄")
    for i, turn in enumerate(turns, 1):
        if turn.get("error"):
            errors.append(f"{cid}: 第 {i} 輪有錯誤：{turn['error']}")
        answer = (turn.get("assistant") or "").strip()
        if not answer:
            errors.append(f"{cid}: 第 {i} 輪沒有回答")
        # 整輪紀錄都會顯示在案例頁（分析步驟、引用課程、來源），所以每個欄位都要檢查
        for field, text in iter_strings(turn):
            for label, pattern in PII_PATTERNS.items():
                if pattern.search(text):
                    errors.append(f"{cid}: 第 {i} 輪 {field} 疑似含 {label}，請人工確認")
    if case["assistant"] == "research":
        project = (case["input"] or {}).get("project") or {}
        if not project.get("id"):
            errors.append(f"{cid}: 研究助理案例缺少 input.project.id")
        if "studentName" in project:
            errors.append(f"{cid}: input.project 不可包含 studentName")
        name = student_names.get(project.get("id", ""), "").strip()
        if len(name) >= 2 and any(name in text for t in turns for _, text in iter_strings(t)):
            errors.append(f"{cid}: 對話紀錄中出現計畫學生姓名，請匿名化")
    review = case["review"] or {}
    if require_approved and (review.get("status") != "approved" or not review.get("reviewer")):
        errors.append(f"{cid}: 尚未人工檢查（review.status={review.get('status')}）")
    return errors


def check_coverage(cases: list[dict]) -> list[str]:
    errors = []
    course = sum(1 for c in cases if c.get("assistant") == "course")
    research = sum(1 for c in cases if c.get("assistant") == "research")
    if len(cases) < MIN_TOTAL:
        errors.append(f"案例數 {len(cases)} < {MIN_TOTAL}")
    if course < MIN_COURSE:
        errors.append(f"課程助理案例 {course} < {MIN_COURSE}")
    if research < MIN_RESEARCH:
        errors.append(f"研究助理案例 {research} < {MIN_RESEARCH}")
    missing = CATEGORIES - {c.get("category") for c in cases}
    if missing:
        errors.append(f"缺少情境分類：{sorted(missing)}")
    ids = [c.get("id") for c in cases]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errors.append(f"案例 id 重複：{sorted(dup)}")
    return errors


def load_student_names() -> dict[str, str]:
    path = ROOT / "data" / "processed" / "projects.json"
    if not path.exists():
        return {}
    return {p["id"]: p.get("studentName", "") for p in json.loads(path.read_text(encoding="utf-8"))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=CASES_DIR)
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()

    files = sorted(args.dir.glob("*.json"))
    cases, errors = [], []
    for f in files:
        try:
            case = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{f.name}: JSON 解析失敗：{exc}")
            continue
        if case.get("id") != f.stem:
            errors.append(f"{f.name}: 檔名與 id（{case.get('id')}）不一致")
        cases.append(case)
    names = load_student_names()
    for case in cases:
        errors.extend(check_case(case, student_names=names, require_approved=args.require_approved))
    errors.extend(check_coverage(cases))

    approved = sum(1 for c in cases if (c.get("review") or {}).get("status") == "approved")
    print(f"案例 {len(cases)} 組，已人工檢查 {approved} 組")
    if errors:
        print("✗ 未通過：")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("✓ 通過")


if __name__ == "__main__":
    main()
