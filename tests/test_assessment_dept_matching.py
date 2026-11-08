import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.schemas import SubjectSelectionRequest  # noqa: E402
from app.routes import assessment  # noqa: E402
from app.services.department_names import dept_key, dept_tracks  # noqa: E402

ALL_SUBJECTS = ["chinese", "english", "math_a", "math_b", "social", "science"]


def _questions(mode):
    return asyncio.run(assessment.get_questions(assessment.AssessmentMode(mode)))


def _filter(subjects):
    return asyncio.run(
        assessment.filter_departments_by_subjects(SubjectSelectionRequest(subjects=subjects))
    )


class DeptKeyTests(unittest.TestCase):
    def test_variants_share_key(self):
        self.assertEqual(dept_key("生命科學學系"), dept_key("生命科學系"))
        self.assertEqual(dept_key("企管學系"), dept_key("企業管理學系"))
        self.assertEqual(dept_key("數學系數學科學組"), dept_key("數學系"))
        self.assertEqual(dept_key("機械工程學系光機電工程組"), dept_key("機械工程學系"))
        self.assertEqual(
            dept_key("客家語文暨社會科學學系客家社會及政策組"), dept_key("客家語文暨社會科學學系")
        )


class AssessmentCoverageTests(unittest.TestCase):
    def test_every_bank_dept_has_a_track(self):
        for mode in ("grade1", "grade2", "grade3"):
            for q in _questions(mode):
                self.assertTrue(dept_tracks(q["department"]), q["department"])

    def test_grade2_tracks_cover_all_cards(self):
        qs = _questions("grade2")
        covered = {q["id"] for q in qs if q["tracks"]}
        self.assertEqual(covered, {q["id"] for q in qs})

    def test_grade3_all_subjects_unlocks_all_cards(self):
        resp = _filter(ALL_SUBJECTS)
        self.assertEqual(resp["unmatched"], [])
        allowed = set(resp["departments"])
        qs = _questions("grade3")
        self.assertEqual([q["id"] for q in qs if q["department"] not in allowed], [])

    def test_grade3_typical_combos_have_no_unmatched(self):
        for subjects in (
            ["chinese", "english", "math_a", "science"],
            ["english", "math_a", "science"],
            ["chinese", "english", "math_b", "social"],
            ["chinese", "english", "social"],
        ):
            self.assertEqual(_filter(subjects)["unmatched"], [], subjects)


if __name__ == "__main__":
    unittest.main()
