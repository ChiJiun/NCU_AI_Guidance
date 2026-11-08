import collections
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("build_glossary", ROOT / "scripts" / "nlp" / "build_glossary.py")
bg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bg)


def _course(*pairs):
    return {"simplified_concepts": [{"original": o, "display": d} for o, d in pairs]}


class Normalisation(unittest.TestCase):
    def test_variant_spellings_share_a_key(self):
        same = [("神經網絡", "神經網路"), ("FOR迴圈", "for 迴圈"), ("輸入/輸出", "輸入輸出"),
                ("卷積神經網路（CNN）", "卷積神經網路"), ("ＮＰ完備性", "NP完備性")]
        for a, b in same:
            self.assertEqual(bg.norm_key(a), bg.norm_key(b), (a, b))

    def test_different_terms_keep_different_keys(self):
        self.assertNotEqual(bg.norm_key("機率論"), bg.norm_key("統計學"))

    def test_cluster_merges_aliases_and_counts_distinct_courses(self):
        data = {"A": _course(("神經網絡", "x")), "B": _course(("神經網路", "y")),
                "C": _course(("神經網路", "y"), ("神經網路", "y"))}
        cl = bg.cluster_terms(data)
        key = bg.norm_key("神經網路")
        self.assertEqual(len(cl), 1)
        self.assertEqual(cl[key]["courses"], {"A", "B", "C"})
        self.assertEqual(bg.canonical_surface(cl[key]["surfaces"]), "神經網路")   # 最常見的寫法

    def test_canonical_gloss_is_most_common_then_shortest(self):
        g = collections.Counter({"長一點的說法": 2, "短說法": 2, "少見": 1})
        self.assertEqual(bg.canonical_gloss(g), "短說法")


class SimplifiedCleanup(unittest.TestCase):
    def test_every_fix_is_traditional_and_actually_different(self):
        for wrong, right in bg.SIMPLIFIED_FIXES.items():
            self.assertTrue(any(ch in bg.SIMPLIFIED_ONLY for ch in wrong), wrong)
            self.assertFalse(any(ch in bg.SIMPLIFIED_ONLY for ch in right), right)

    def test_cluster_replaces_simplified_terms(self):
        cl = bg.cluster_terms({"A": _course(("气候系统", "研究氣候的系統"))})
        self.assertEqual([bg.canonical_surface(v["surfaces"]) for v in cl.values()], ["氣候系統"])


class Selection(unittest.TestCase):
    def _clusters(self):
        data = {f"C{i}": _course(("常見詞", "a")) for i in range(4)}
        data.update({f"D{i}": _course(("冷門詞", "b")) for i in range(2)})
        data.update({f"E{i}": _course(("這其實是一整句很長很長的話而不是名詞", "c")) for i in range(5)})
        return bg.cluster_terms(data)

    def test_core_needs_enough_courses_and_a_noun_sized_term(self):
        keys = bg.select_core(self._clusters(), forced=[])
        self.assertEqual(keys, [bg.norm_key("常見詞")])

    def test_forced_terms_are_always_included_even_if_absent_from_data(self):
        keys = bg.select_core(self._clusters(), forced=["單元操作"])
        self.assertIn(bg.norm_key("單元操作"), keys)

    def test_every_forced_term_normalises_to_a_nonempty_key(self):
        for t in bg.FORCED_TERMS:
            self.assertTrue(bg.norm_key(t), t)


class QualityChecks(unittest.TestCase):
    OK = {"gloss": "用現在的狀態預測下一步的機率模型", "hs_link": "高中數學：機率", "type": "概念",
          "skip": False, "uncertain": False}

    def test_good_entry_passes(self):
        self.assertEqual(bg.check_entry("馬可夫鏈", self.OK), [])

    def test_each_failure_mode_is_caught(self):
        cases = {
            "循環": {**self.OK, "gloss": "馬可夫鏈是一種機率模型的說法"},
            "太短": {**self.OK, "gloss": "機率"},
            "太長": {**self.OK, "gloss": "這是一個說明文字非常非常非常非常非常長而且一直講下去的描述還有很多很多字"},
            "簡體": {**self.OK, "gloss": "用现在的状态预测下一步的模型"},
            "提到課程": {**self.OK, "gloss": "這門課會教你預測下一步"},
            "hs 格式": {**self.OK, "hs_link": "數學"},
            "type": {**self.OK, "type": "其他"},
        }
        for name, entry in cases.items():
            self.assertTrue(bg.check_entry("馬可夫鏈", entry), name)

    def test_traditional_text_with_valid_characters_is_not_flagged(self):
        entry = {**self.OK, "gloss": "管理電腦資源的系統軟體"}   # 「系」不能被當成簡體字
        self.assertEqual(bg.check_entry("作業系統", entry), [])

    def test_skip_and_uncertain_entries_are_not_checked(self):
        self.assertEqual(bg.check_entry("資料分析", {"skip": True}), [])
        self.assertEqual(bg.check_entry("某個詞", {"uncertain": True, "gloss": None}), [])


class Assemble(unittest.TestCase):
    def _setup(self):
        data = {f"C{i}": _course(("馬可夫鏈", "舊說明甲")) for i in range(4)}
        data.update({"X": _course(("冷門詞", "舊說明乙"))})
        clusters = bg.cluster_terms(data)
        return clusters, bg.select_core(clusters, forced=[])

    def test_good_generation_becomes_core_and_rest_is_fallback(self):
        clusters, core = self._setup()
        gen = {bg.norm_key("馬可夫鏈"): {**QualityChecks.OK, "term": "馬可夫鏈"}}
        terms, stats = bg.assemble(clusters, core, gen)
        self.assertEqual(terms["馬可夫鏈"]["tier"], "core")
        self.assertEqual(terms["馬可夫鏈"]["gloss"], QualityChecks.OK["gloss"])
        self.assertEqual(terms["冷門詞"]["tier"], "fallback")
        self.assertEqual(terms["冷門詞"]["gloss"], "舊說明乙")
        self.assertEqual(stats, {"fallback": 1, "core_ok": 1})

    def test_bad_generation_falls_back_and_is_marked_for_review(self):
        clusters, core = self._setup()
        gen = {bg.norm_key("馬可夫鏈"): {**QualityChecks.OK, "term": "馬可夫鏈", "gloss": "机率"}}
        terms, stats = bg.assemble(clusters, core, gen)
        self.assertEqual(terms["馬可夫鏈"]["gloss"], "舊說明甲")
        self.assertTrue(terms["馬可夫鏈"]["needs_review"])
        self.assertEqual(stats["core_needs_review"], 1)

    def test_uncertain_and_missing_generation_need_review(self):
        clusters, core = self._setup()
        for gen in ({bg.norm_key("馬可夫鏈"): {"term": "馬可夫鏈", "uncertain": True, "gloss": None}}, {}):
            terms, _ = bg.assemble(clusters, core, gen)
            self.assertTrue(terms["馬可夫鏈"]["needs_review"])

    def test_forced_term_missing_from_data_is_still_listed(self):
        clusters = bg.cluster_terms({"A": _course(("別的詞", "x"))})
        core = bg.select_core(clusters, forced=["OpenCV"])
        gen = {bg.norm_key("OpenCV"): {"term": "OpenCV", "gloss": "常用來處理影像的程式函式庫",
                                       "hs_link": None, "type": "技術或工具", "skip": False, "uncertain": False}}
        terms, _ = bg.assemble(clusters, core, gen)
        self.assertEqual(terms["OpenCV"]["tier"], "core")


class CrossReviewPolicy(unittest.TestCase):
    K = bg.norm_key("泰勒級數")

    def _gen(self, **over):
        return {self.K: {"term": "泰勒級數", "gloss": "把函數寫成一串由低到高次方項相加的近似式",
                         "hs_link": "高中數學：多項式函數", "type": "概念", "skip": False, "uncertain": False,
                         "_model": "claude-sonnet-5-5", **over}}

    def test_ok_review_keeps_claude_version_but_only_confirmed_hs_link(self):
        out = bg.apply_reviews(self._gen(), {self.K: {"verdict": "ok", "hs_ok": False}}, {}, {})
        self.assertIsNone(out[self.K]["hs_link"])                      # GPT 認為牽強 → 移除
        self.assertEqual(out[self.K]["_verified"], "claude+gpt")
        out = bg.apply_reviews(self._gen(), {self.K: {"verdict": "ok", "hs_ok": True}}, {}, {})
        self.assertEqual(out[self.K]["hs_link"], "高中數學：多項式函數")   # 兩個模型都同意 → 保留

    def test_unreviewed_entries_never_keep_hs_link(self):
        out = bg.apply_reviews(self._gen(), {}, {}, {})
        self.assertIsNone(out[self.K]["hs_link"])
        self.assertEqual(out[self.K]["_verified"], "claude-only")

    def test_refined_version_is_used_only_if_the_second_review_passes(self):
        r1 = {self.K: {"verdict": "inaccurate", "comment": "不是只有多項式", "hs_ok": False}}
        refined = {self.K: {"term": "泰勒級數", "gloss": "用很多項相加來逼近複雜函數的方法", "hs_link": None,
                            "type": "概念", "skip": False, "uncertain": False}}
        good = bg.apply_reviews(self._gen(), r1, refined, {self.K: {"verdict": "ok", "hs_ok": None}})
        self.assertEqual(good[self.K]["gloss"], "用很多項相加來逼近複雜函數的方法")
        self.assertEqual(good[self.K]["_verified"], "claude+gpt(改寫後)")
        bad = bg.apply_reviews(self._gen(), r1, refined, {self.K: {"verdict": "too_hard"}})
        self.assertTrue(bad[self.K]["uncertain"])                       # 仍未通過 → 待人工確認
        self.assertIn("inaccurate", bad[self.K]["_note"])

    def test_ambiguous_terms_are_not_auto_annotated(self):
        out = bg.apply_reviews(self._gen(), {self.K: {"verdict": "ambiguous", "comment": "數學與程式意思不同"}}, {}, {})
        self.assertTrue(out[self.K]["skip"])

    def test_needs_rewrite_only_for_fixable_verdicts(self):
        for v in ("inaccurate", "too_hard", "vague"):
            self.assertTrue(bg.needs_rewrite({"verdict": v}))
        for v in ("ok", "ambiguous"):
            self.assertFalse(bg.needs_rewrite({"verdict": v}))
        self.assertFalse(bg.needs_rewrite(None))

    def test_assemble_carries_verification_status(self):
        clusters = bg.cluster_terms({f"C{i}": _course(("馬可夫鏈", "舊")) for i in range(4)})
        core = bg.select_core(clusters, forced=[])
        gen = {bg.norm_key("馬可夫鏈"): {**QualityChecks.OK, "term": "馬可夫鏈", "_verified": "claude+gpt"}}
        terms, _ = bg.assemble(clusters, core, gen)
        self.assertEqual(terms["馬可夫鏈"]["verified"], "claude+gpt")


class ParsingClaudeOutput(unittest.TestCase):
    def test_items_must_match_the_requested_terms_in_order(self):
        text = '前言 {"items":[{"term":"甲"},{"term":"乙"}]} 後記'
        self.assertEqual(len(bg.parse_items(text, ["甲", "乙"])), 2)
        self.assertIsNone(bg.parse_items(text, ["乙", "甲"]))
        self.assertIsNone(bg.parse_items(text, ["甲"]))
        self.assertIsNone(bg.parse_items("不是 json", ["甲"]))

    def test_trailing_text_with_braces_after_the_json_is_ignored(self):
        # 回歸：模型在 JSON 後面多附說明（含大括號）時，舊作法取「最後一個 }」會解析失敗
        text = '{"items":[{"term":"甲"}]}\n\n備註：格式為 {"items": [...]}，共 1 筆。'
        self.assertEqual(len(bg.parse_items(text, ["甲"])), 1)


class ManualReview(unittest.TestCase):
    def _terms(self):
        return {
            "量子糾纏": {"gloss": "粒子間的神秘連接", "skip": False, "needs_review": True, "review_reason": "x"},
            "聲子": {"gloss": "聲波的量子", "skip": True, "needs_review": True},
            "繼承": {"gloss": "死後財產轉移", "skip": True, "needs_review": True},
            "傳輸層": {"gloss": "資料傳輸控制層", "skip": False, "needs_review": True},
        }

    def test_rewrite_replaces_the_gloss_and_clears_skip_and_review(self):
        terms = self._terms()
        stats = bg.apply_manual(terms, {"rewrite": {"聲子": "固體中原子集體振動的最小能量單位"}, "skip": ["繼承"]})
        self.assertEqual(terms["聲子"]["gloss"], "固體中原子集體振動的最小能量單位")
        self.assertFalse(terms["聲子"]["skip"])
        self.assertNotIn("needs_review", terms["聲子"])
        self.assertEqual(stats["rewritten"], 1)

    def test_skip_list_keeps_the_term_out_of_annotation(self):
        terms = self._terms()
        bg.apply_manual(terms, {"skip": ["繼承"]})
        self.assertTrue(terms["繼承"]["skip"])
        self.assertNotIn("needs_review", terms["繼承"])

    def test_untouched_review_terms_with_a_gloss_are_approved(self):
        terms = self._terms()
        stats = bg.apply_manual(terms, {})
        self.assertNotIn("needs_review", terms["傳輸層"])
        self.assertEqual(terms["傳輸層"]["verified"], "claude-manual")
        self.assertEqual(stats["approved"], 2)   # 量子糾纏、傳輸層；聲子與繼承本來就是 skip

    def test_a_rewrite_that_fails_the_checks_is_rejected(self):
        terms = self._terms()
        stats = bg.apply_manual(terms, {"rewrite": {"量子糾纏": "量子糾纏是兩個粒子的關係"}})   # 循環解釋
        self.assertEqual(terms["量子糾纏"]["gloss"], "粒子間的神秘連接")
        self.assertEqual(stats["rejected"], 1)


if __name__ == "__main__":
    unittest.main()
