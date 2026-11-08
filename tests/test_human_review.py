import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "test_course_agent"))

import human_review as H  # noqa: E402


def _j(verdicts, score):
    return {"checks": [{"id": i, "verdict": v, "evidence": ""} for i, v in enumerate(verdicts, 1)],
            "scores": {k: score for k in H.J.DIMENSIONS}, "reasons": {}, "flags": [], "needs_human_check": []}


SHEET = """
## 1. A01｜問題
<!-- review:A01 -->
| # | 檢查點 | 達成？（填 ✓ 或 ✗） | 備註 |
|---|---|---|---|
| 1 | 第一條 | ✓ |  |
| 2 | 第二條 | x | 少了課程 |
| 面向 | 我的分數（0–2） | 備註 |
|---|---|---|
| 切題 | 2 |  |
| 正確與誠實 | 1 |  |
| 高中生看得懂 | 2 |  |
| 引導探索 | 2 |  |
<details>
| 1 | ✗ | AI 的證據 | ✗ |
| 切題 | 0 | AI 理由 | 0 |
</details>
## 2. B01｜問題
<!-- review:B01 -->
| 1 | 第一條 |  |  |
| 切題 |  |  |
"""


class HumanReview(unittest.TestCase):
    def test_sample_is_reproducible_and_splits_each_group_at_the_median(self):
        scores = {f"{g}{i:02d}": float(i) for g in "AB" for i in range(1, 11)}
        groups = {k: k[0] for k in scores}
        s1 = H.pick_sample(scores, groups, 20261109)
        self.assertEqual(s1, H.pick_sample(scores, groups, 20261109))
        self.assertEqual(len(s1), 4)
        for lo, hi in (s1[0:2], s1[2:4]):
            self.assertLessEqual(scores[lo], 5.5)
            self.assertGreater(scores[hi], 5.5)

    def test_sample_handles_ties(self):
        scores = {"A01": 1.0, "A02": 1.0, "A03": 1.0}
        picked = H.pick_sample(scores, {k: "A" for k in scores}, 1)
        self.assertEqual(len(set(picked)), 2)

    def test_parse_sheet_reads_only_the_blind_part(self):
        got = H.parse_sheet(SHEET)
        self.assertEqual(got["A01"]["checks"], {1: "met", 2: "not_met"})
        self.assertEqual(got["A01"]["scores"], {"relevance": 2, "honesty": 1, "readable": 2, "guidance": 2})
        self.assertEqual(got["B01"], {"checks": {}, "scores": {}})

    def test_agreement_against_each_pass(self):
        human = H.parse_sheet(SHEET)
        ai = {"A01": [_j(["met", "met"], 2), _j(["met", "not_met"], 1)]}
        a1 = H.agreement(human, ai, 0)
        self.assertEqual((a1["questions"], a1["check_items"], a1["check_agree"]), (1, 2, 50.0))
        self.assertEqual((a1["total_exact"], a1["total_within_1"]), (0.0, 100.0))  # 7 vs 8
        a2 = H.agreement(human, ai, 1)
        self.assertEqual(a2["check_agree"], 100.0)
        self.assertEqual(a2["dim_exact"]["honesty"], 100.0)

    def test_cohen_kappa(self):
        self.assertEqual(H.cohen_kappa([("met", "met"), ("not_met", "not_met")]), 1.0)
        self.assertEqual(H.cohen_kappa([("met", "not_met"), ("not_met", "met")]), -1.0)
        self.assertIsNone(H.cohen_kappa([("met", "met")]))
        self.assertIsNone(H.cohen_kappa([]))


if __name__ == "__main__":
    unittest.main()
