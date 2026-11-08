import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("export_glossary_frontend", ROOT / "scripts" / "nlp" / "export_glossary_frontend.py")
eg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eg)


def _entry(gloss="說明", **kw):
    return {"gloss": gloss, "skip": False, "tier": "core", "n_courses": 1, "aliases": [], **kw}


class SelectTerms(unittest.TestCase):
    def test_core_and_manually_reviewed_terms_are_exported(self):
        terms = {"甲甲": _entry(), "乙乙": _entry(tier="fallback", verified="claude-manual")}
        self.assertEqual(set(eg.select_terms(terms)), {"甲甲", "乙乙"})

    def test_unreviewed_fallback_terms_are_not_exported(self):
        self.assertEqual(eg.select_terms({"甲甲": _entry(tier="fallback")}), {})

    def test_skipped_and_needs_review_terms_are_not_exported(self):
        terms = {"甲甲": _entry(skip=True), "乙乙": _entry(needs_review=True), "丙丙": _entry(gloss="")}
        self.assertEqual(eg.select_terms(terms), {})

    def test_aliases_get_the_same_gloss(self):
        out = eg.select_terms({"神經網路": _entry("像大腦一樣分層運算的模型", aliases=["神經網絡"])})
        self.assertEqual(out["神經網絡"], out["神經網路"])

    def test_one_character_surfaces_are_dropped(self):
        self.assertEqual(eg.select_terms({"熵": _entry()}), {})

    def test_conflicting_surface_keeps_the_gloss_used_by_more_courses(self):
        terms = {"甲甲": _entry("少", n_courses=1, aliases=["同名"]), "乙乙": _entry("多", n_courses=9, aliases=["同名"])}
        self.assertEqual(eg.select_terms(terms)["同名"], "多")


if __name__ == "__main__":
    unittest.main()
