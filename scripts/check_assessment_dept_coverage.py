"""
檢查興趣量表各模式可用的題卡數，以及系所名稱是否都能配對。

用法（在 project/ 底下）：
    python scripts/check_assessment_dept_coverage.py

  - 高一：所有 grade1 題卡
  - 高二文組 / 理組：依 dept_tracks() 分組；列出沒有被分到任何組的題庫系所
  - 高三：用 /assessment/filter-by-subjects 相同邏輯，列出全選科目與典型組合
          可用題卡數、未配對的招生系所、合理排除的招生系所
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.schemas import SubjectSelectionRequest  # noqa: E402
from app.routes import assessment  # noqa: E402
from app.services.department_names import EXCLUDED_ADMISSION, dept_tracks  # noqa: E402

SUBJECT_COMBOS = {
    "全選": ["chinese", "english", "math_a", "math_b", "social", "science"],
    "自然組 國英數A自": ["chinese", "english", "math_a", "science"],
    "自然組 英數A自": ["english", "math_a", "science"],
    "社會組 國英數B社": ["chinese", "english", "math_b", "social"],
    "社會組 國英社": ["chinese", "english", "social"],
    "跨考 國英數A社自": ["chinese", "english", "math_a", "social", "science"],
}


def questions(mode: str):
    return asyncio.run(assessment.get_questions(assessment.AssessmentMode(mode)))


def grade2_report():
    qs = questions("grade2")
    result = {}
    for track in ("liberal", "science"):
        result[track] = [q for q in qs if track in q["tracks"]]
    untracked = sorted({q["department"] for q in qs if not dept_tracks(q["department"])})
    return qs, result, untracked


def grade3_report(subjects):
    qs = questions("grade3")
    resp = asyncio.run(
        assessment.filter_departments_by_subjects(SubjectSelectionRequest(subjects=subjects))
    )
    allowed = set(resp["departments"])
    usable = [q for q in qs if q["department"] in allowed]
    return qs, usable, resp


def main() -> int:
    ok = True
    g1 = questions("grade1")
    print(f"[高一] 題卡 {len(g1)} 張（不分組，全部可用）")

    g2, tracks, untracked = grade2_report()
    print(f"\n[高二] 題庫共 {len(g2)} 張")
    for track, label in (("liberal", "文組"), ("science", "理組")):
        depts = sorted({q["department"] for q in tracks[track]})
        print(f"  {label}：{len(tracks[track])} 張，{len(depts)} 個系所")
    print(f"  未分組系所：{untracked or '無'}")
    ok &= not untracked

    print(f"\n[高三] 題庫共 {len(questions('grade3'))} 張")
    for label, subjects in SUBJECT_COMBOS.items():
        _, usable, resp = grade3_report(subjects)
        print(
            f"  {label:<18} 可用 {len(usable):>2} 張 | 符合招生系所 {len(resp['admission_departments'])}"
            f" | 未配對 {resp['unmatched'] or '無'}"
        )
        if resp["excluded"]:
            print(f"  {'':<18} 合理排除 {resp['excluded']}")
        ok &= not resp["unmatched"]

    print("\n合理排除理由：")
    for name, reason in EXCLUDED_ADMISSION.items():
        print(f"  - {name}：{reason}")

    print("\n結果：", "OK" if ok else "有未配對系所")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
