"""興趣量表抽題與評分：題數上限、各系平均、可重現、評分不受題卡數影響。"""
import asyncio
import sys
import unittest
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.schemas import Answer, AssessmentMode, SubmitAnswersRequest  # noqa: E402
from app.routes import assessment  # noqa: E402
from app.services.department_names import dept_tracks  # noqa: E402

ALL_SUBJECTS = ["chinese", "english", "math_a", "math_b", "social", "science"]
LIMIT = assessment.CARDS_PER_ATTEMPT
CASES = [
    ("grade1", None, None),
    ("grade2", "liberal", None),
    ("grade2", "science", None),
    ("grade3", None, ALL_SUBJECTS),
    ("grade3", None, ["chinese", "english", "math_a", "science"]),
    ("grade3", None, ["chinese", "english", "math_b", "social"]),
    ("grade3", None, ["chinese", "english", "social"]),
]


def _submit(answers):
    req = SubmitAnswersRequest(mode=AssessmentMode.GRADE2, answers=[
        Answer(questionId=qid, score=s) for qid, s in answers
    ])
    return asyncio.run(assessment.submit_answers(req))


class SamplingTests(unittest.TestCase):
    def test_cap_and_one_card_per_department(self):
        for mode, track, subjects in CASES:
            for seed in range(30):
                qs = assessment.select_questions(mode, track, subjects, seed=seed)
                counts = Counter(q["department"] for q in qs)
                self.assertLessEqual(len(qs), LIMIT, (mode, track, subjects))
                self.assertEqual(set(counts.values()), {1}, (mode, track, subjects))

    def test_small_pools_show_every_department(self):
        qs = assessment.select_questions("grade2", "liberal", seed=1)
        pool = {q["department"] for q in assessment.mode_cards("grade2") if "liberal" in q["tracks"]}
        self.assertEqual({q["department"] for q in qs}, pool)

    def test_grade1_balances_tracks(self):
        for seed in range(30):
            qs = assessment.select_questions("grade1", seed=seed)
            tracks = Counter(tuple(dept_tracks(q["department"])) for q in qs)
            self.assertEqual(tracks, Counter({("liberal",): LIMIT // 2, ("science",): LIMIT // 2}))

    def test_grade2_science_spans_every_college(self):
        pool = {assessment.dept_college(q["department"])
                for q in assessment.mode_cards("grade2") if "science" in q["tracks"]}
        for seed in range(30):
            qs = assessment.select_questions("grade2", "science", seed=seed)
            self.assertEqual({assessment.dept_college(q["department"]) for q in qs}, pool)

    def test_same_seed_same_questions(self):
        for mode, track, subjects in CASES:
            a = [q["id"] for q in assessment.select_questions(mode, track, subjects, seed=123)]
            b = [q["id"] for q in assessment.select_questions(mode, track, subjects, seed=123)]
            self.assertEqual(a, b)

    def test_rotation_covers_whole_bank(self):
        seen = set()
        for seed in range(400):
            seen |= {q["id"] for q in assessment.select_questions("grade2", "science", seed=seed)}
        pool = {q["id"] for q in assessment.mode_cards("grade2") if "science" in q["tracks"]}
        self.assertEqual(seen, pool)


class EligibilityTests(unittest.TestCase):
    def test_all_subjects_means_all_departments(self):
        allowed = set(assessment.eligible_bank_departments(ALL_SUBJECTS)["departments"])
        bank = {q["department"] for q in assessment.mode_cards("grade3")}
        self.assertEqual(allowed, bank)

    def test_more_subjects_never_removes_departments(self):
        for k in range(1, len(ALL_SUBJECTS)):
            for subset in combinations(ALL_SUBJECTS, k):
                small = set(assessment.eligible_bank_departments(list(subset))["departments"])
                for extra in set(ALL_SUBJECTS) - set(subset):
                    big = set(assessment.eligible_bank_departments(list(subset) + [extra])["departments"])
                    self.assertLessEqual(small, big, (subset, extra))


class ScoringTests(unittest.TestCase):
    def test_department_score_is_mean_not_sum(self):
        cards = assessment.mode_cards("grade2")
        by_dept = Counter(q["department"] for q in cards)
        big = next(d for d, n in by_dept.items() if n >= 3)
        small = next(d for d, n in by_dept.items() if n == 1)
        big_cards = [q["id"] for q in cards if q["department"] == big][:3]
        small_card = next(q["id"] for q in cards if q["department"] == small)
        answers = [(qid, 4) for qid in big_cards for _ in range(3)]
        answers += [(small_card, 5)] * 3
        res = _submit(answers)
        self.assertEqual(res.departments[0].name, small)
        self.assertEqual(res.departments[1].score, 4.0)

    def test_tag_scores_stay_on_1_to_5_scale(self):
        cards = assessment.mode_cards("grade2")
        answers = [(q["id"], 5) for q in cards[:10] for _ in range(3)]
        res = _submit(answers)
        self.assertTrue(all(1 <= t.score <= 5 for t in res.tagScores))
        self.assertTrue(all(t.score == 5 for t in res.tagScores))

    def test_track_scores(self):
        qs = assessment.select_questions("grade1", seed=5)
        answers = [(q["id"], 5 if q["tracks"] == ["liberal"] else 2) for q in qs for _ in range(3)]
        res = _submit(answers)
        self.assertEqual(res.trackScores.liberal, 5)
        self.assertEqual(res.trackScores.science, 2)


if __name__ == "__main__":
    unittest.main()
