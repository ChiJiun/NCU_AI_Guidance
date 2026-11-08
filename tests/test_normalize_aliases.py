import collections
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("normalize_aliases", ROOT / "scripts" / "nlp" / "normalize_aliases.py")
na = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(na)


def _map(**uses):
    mapping, groups = na.build_map(collections.Counter(uses))
    return mapping, groups


class MergeRules(unittest.TestCase):
    def test_spelling_variants_are_merged(self):
        m, _ = na.build_map(collections.Counter({"神經網絡": 3, "神經網路": 5, "for 迴圈": 1, "FOR迴圈": 2}))
        self.assertEqual(m["神經網絡"], "神經網路")
        self.assertEqual(m["for 迴圈"], "FOR迴圈")

    def test_bare_form_wins_and_absorbs_bracketed_forms(self):
        m, _ = na.build_map(collections.Counter(
            {"大型語言模型": 5, "大型語言模型（LLM）": 9, "大型語言模型（LLMs）": 2}))
        self.assertEqual(m["大型語言模型（LLM）"], "大型語言模型")
        self.assertEqual(m["大型語言模型（LLMs）"], "大型語言模型")

    def test_chinese_qualifier_is_absorbed_when_a_bare_form_exists(self):
        m, _ = na.build_map(collections.Counter({"大氣科學": 40, "大氣科學(微波遙測)": 3}))
        self.assertEqual(m["大氣科學(微波遙測)"], "大氣科學")

    def test_enumerated_items_are_never_merged(self):
        m, _ = na.build_map(collections.Counter(
            {"企業舞弊案例(一)": 2, "企業舞弊案例(二)": 2, "企業舞弊案例(三)": 2}))
        self.assertEqual(m, {})

    def test_different_bracketed_topics_without_a_bare_form_stay_apart(self):
        m, _ = na.build_map(collections.Counter({"形容詞（性數變化）": 2, "形容詞（形容詞協調）": 2}))
        self.assertEqual(m, {})

    def test_leading_bracket_is_part_of_the_word(self):
        m, _ = na.build_map(collections.Counter({"民族主義": 5, "(跨)民族主義": 2}))
        self.assertEqual(m, {})

    def test_same_bracket_content_in_different_widths_is_merged(self):
        m, _ = na.build_map(collections.Counter({"MRP II（物料需求計劃 II）": 2, "MRP-II（物料需求計劃 II）": 2}))
        self.assertEqual(len(m), 1)

    def test_simplified_terms_are_converted_even_without_a_traditional_twin(self):
        m, _ = na.build_map(collections.Counter({"关键带": 2}))
        self.assertEqual(m["关键带"], "關鍵帶")

    def test_mapping_never_points_to_another_mapped_term(self):
        # 對照表要一步到位：目標本身不能再被改寫，否則重跑會不冪等
        m, _ = na.build_map(collections.Counter(
            {"神經網絡": 3, "神經網路": 5, "神經網路（NN）": 1, "关键带": 2, "關鍵帶": 1}))
        for src, dst in m.items():
            self.assertNotIn(dst, m, (src, dst))


class ApplyConsistently(unittest.TestCase):
    def test_map_list_dedupes_and_keeps_order(self):
        self.assertEqual(na.map_list(["神經網絡", "深度學習", "神經網路"], {"神經網絡": "神經網路"}),
                         ["神經網路", "深度學習"])

    def test_merge_fields_keeps_highest_relevance_and_unions_professors(self):
        entries = [{"field": "大氣科學(微波遙測)", "relevance": "medium", "professors": ["甲"]},
                   {"field": "大氣科學", "relevance": "high", "professors": ["乙", "甲"]}]
        out = na.merge_fields(entries, {"大氣科學(微波遙測)": "大氣科學"}, union_key="professors")
        self.assertEqual(out, [{"field": "大氣科學", "relevance": "high", "professors": ["甲", "乙"]}])

    def test_all_files_use_the_same_field_names_after_applying(self):
        maps = {"concept": {}, "technology": {}, "field": {"大氣科學(微波遙測)": "大氣科學"}}
        tech, simp = {}, {}
        domain = {"A": {"domain_tags": [{"field": "大氣科學(微波遙測)", "relevance": "high"}]}}
        prof = {"A": [{"field": "大氣科學(微波遙測)", "professors": ["甲"], "relevance": "high"}]}
        dept = {"大氣系": {"specialty_vocab": ["大氣科學(微波遙測)", "大氣科學"]}}
        na.apply_all(maps, tech, domain, prof, dept, simp)
        self.assertEqual(domain["A"]["domain_tags"][0]["field"], "大氣科學")
        self.assertEqual(prof["A"][0]["field"], "大氣科學")
        self.assertEqual(dept["大氣系"]["specialty_vocab"], ["大氣科學"])

    def test_technology_and_concept_maps_are_applied_to_the_right_lists(self):
        maps = {"concept": {"神經網絡": "神經網路"}, "technology": {"python": "Python"}, "field": {}}
        tech = {"C1": {"concepts": ["神經網絡"], "languages": ["python"], "tools": ["Python"]}}
        simp = {"C1": {"simplified_concepts": [{"original": "神經網絡", "display": "x"},
                                               {"original": "神經網路", "display": "y"}]}}
        na.apply_all(maps, tech, {}, {}, {}, simp)
        self.assertEqual(tech["C1"], {"concepts": ["神經網路"], "languages": ["Python"], "tools": ["Python"]})
        self.assertEqual([c["original"] for c in simp["C1"]["simplified_concepts"]], ["神經網路"])

    def test_applying_twice_changes_nothing_more(self):
        counts = collections.Counter({"神經網絡": 3, "神經網路": 5, "SQL": 4, "SQL（結構化查詢語言）": 2})
        m, _ = na.build_map(counts)
        maps = {"concept": m, "technology": {}, "field": {}}
        tech = {"C1": {"concepts": ["神經網絡", "SQL（結構化查詢語言）"], "languages": [], "tools": []}}
        na.apply_all(maps, tech, {}, {}, {}, {})
        once = repr(tech)
        na.apply_all(maps, tech, {}, {}, {}, {})
        self.assertEqual(once, repr(tech))


if __name__ == "__main__":
    unittest.main()
