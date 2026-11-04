"""
make_score_sheet.py — 從一次評估結果產生給評分者的空白評分表（CSV，Excel 可直接開）

每位評分者各拿一份，獨立評分、不要互相參考。評分標準見 docs/evaluation/rubric.md。

用法：
  python scripts/evaluation/make_score_sheet.py data/evaluation/runs/<run_id> --raters A B
輸出：<run_dir>/score_A.csv、score_B.csv
評完後：python scripts/evaluation/analyze_scores.py data/evaluation/runs/<run_id>
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_SET = ROOT / "data" / "evaluation" / "test_set.json"

DIMENSIONS = ["correctness", "traceability", "completion", "safety"]
SCORE_COLUMNS = DIMENSIONS + ["error_types", "notes"]
COLUMNS = ["id", "assistant", "category", "difficulty", "question", "answer", "process", "citations",
           "reference", "expected_behavior", "system_error"] + SCORE_COLUMNS


def _reference_text(item: dict) -> str:
    ref = item.get("reference")
    if not ref:
        return ""
    return "\n".join(f"- {p}" for p in ref.get("answer_points", [])) + f"\n（來源：{ref.get('source', '')}）"


def build_rows(responses: list[dict], test_items: dict[str, dict]) -> list[dict]:
    rows = []
    for r in responses:
        item = test_items.get(r["id"], {})
        citations = list(r.get("course_cards") or []) + [str(s) for s in r.get("sources") or []]
        rows.append({
            "id": r["id"],
            "assistant": r["assistant"],
            "category": r["category"],
            "difficulty": r["difficulty"],
            "question": r["question"],
            "answer": r["answer"],
            "process": "\n".join(r.get("process") or []),
            "citations": "\n".join(citations),
            "reference": _reference_text(item),
            "expected_behavior": item.get("expected_behavior", ""),
            "system_error": r.get("error") or "",
            **{c: "" for c in SCORE_COLUMNS},
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--raters", nargs="+", default=["A", "B"])
    args = parser.parse_args()

    responses = [json.loads(line) for line in (args.run_dir / "responses.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    test_items = {it["id"]: it for it in json.loads(TEST_SET.read_text(encoding="utf-8"))["items"]}
    rows = build_rows(responses, test_items)
    for rater in args.raters:
        path = args.run_dir / f"score_{rater}.csv"
        if path.exists():
            print(f"略過 {path.name}：已存在（避免覆蓋評分）")
            continue
        with path.open("w", encoding="utf-8-sig", newline="") as fh:  # utf-8-sig：Excel 開啟不亂碼
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"✓ {path}")


if __name__ == "__main__":
    main()
