import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "judge_with_claude", ROOT / "scripts" / "test_course_agent" / "judge_with_claude.py")
judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge)

EVAL = json.loads((ROOT / "docs" / "10-retrieval-evaluation" / "eval-set-v1.json").read_text(encoding="utf-8"))
QMAP = {q["id"]: q for q in EVAL["questions"]}
BANNED = set(EVAL["meta"]["tools_must_not_call"])
KNOWN = {judge.normalize_course_name(n) for n in ("資料結構", "物理化學實驗Ⅱ", "臺灣史", "機率與統計")}


def _rec(qid, tools, answer="答案", error="", elapsed=10.0):
    return {"category": qid, "answer": answer, "error": error, "tools_used": list(tools),
            "tool_calls": [{"tool": t, "args": {}, "count": 3, "coursesFound": ["資料結構"]} for t in tools],
            "course_cards": [], "elapsed_sec": elapsed}


def _q(behavior, allow_no_tool=False, checks=("a", "b")):
    return {"id": "X01", "group": "A", "question": "?", "intent": ["探索"], "expected_behavior": behavior,
            "tools": {"all": [], "any": ["search_courses"], "min_calls": {}, "allow_no_tool": allow_no_tool,
                      "multi_tool": False},
            "checks": list(checks), "watch_flags": []}


def _judgement(scores=1, verdicts=("met", "not_met"), flags=()):
    return {"checks": [{"id": i, "verdict": v, "evidence": ""} for i, v in enumerate(verdicts, 1)],
            "scores": {k: scores for k in judge.DIMENSIONS}, "reasons": {},
            "behavior": {"asks_question": False, "corrects_premise": False},
            "flags": list(flags), "needs_human_check": []}


def _row(key, q, rec, judgements=()):
    return {"key": key, "qid": q["id"], "group": q["group"], "question": q["question"], "checks": q["checks"],
            "hard": judge.hard_signals(q, rec, BANNED, KNOWN), "judgements": list(judgements),
            "judge_models": ["claude-sonnet-5-5"] * len(judgements), "judge_errors": []}


class CourseNameNormalisation(unittest.TestCase):
    def test_strips_brackets_spaces_and_trailing_numerals(self):
        n = judge.normalize_course_name
        self.assertEqual(n("資料結構（資訊工程學系）"), "資料結構")
        self.assertEqual(n("物理化學實驗 Ⅱ"), "物理化學實驗")
        self.assertEqual(n("物理化學實驗II"), "物理化學實驗")
        self.assertEqual(n("輸送現象與單元操作(Ⅱ)"), "輸送現象與單元操作")
        self.assertEqual(n("輸送現象與單元操作Ｉ"), "輸送現象與單元操作")
        self.assertEqual(n("線性代數一"), "線性代數")
        self.assertEqual(n("臺灣史"), "台灣史")
        self.assertEqual(n("有機化學 [已停開]"), "有機化學")

    def test_does_not_strip_a_name_to_nothing(self):
        self.assertEqual(judge.normalize_course_name("I"), "I")

    def test_course_tags_report_unknown_names_and_department_tags(self):
        ans = ("<course>資料結構（資工系）</course>、<course>物理化學實驗Ⅰ</course>、"
               "<course>台灣史</course>、<course>量子美食學</course>、<course>資訊工程學系</course>、"
               "<course>人工智慧技術應用學程</course>")
        t = judge.check_course_tags(ans, KNOWN)
        self.assertEqual(t["unknown"], ["量子美食學"])
        self.assertEqual(t["dept_tags"], ["人工智慧技術應用學程", "資訊工程學系"])
        self.assertEqual((t["course_tags"], t["found"], t["unique_courses"]), (4, 3, 4))

    def test_known_courses_include_course_data_and_graph(self):
        known = judge.load_known_courses()
        if not known:
            self.skipTest("本機沒有課程資料")
        self.assertIn("資料結構", known)
        self.assertNotIn("量子美食學", known)


class Behaviour(unittest.TestCase):
    def test_query_requires_a_tool_call(self):
        q = _q("query")
        self.assertTrue(judge.hard_signals(q, _rec("X01", ["search_courses"]), BANNED, KNOWN)["behavior_ok"])
        h = judge.hard_signals(q, _rec("X01", []), BANNED, KNOWN)
        self.assertFalse(h["behavior_ok"])
        self.assertIn("沒有呼叫", h["behavior_problem"])

    def test_banned_tool_does_not_count_as_a_query(self):
        self.assertFalse(judge.hard_signals(_q("query"), _rec("X01", ["get_dept_info"]), BANNED, KNOWN)["behavior_ok"])

    def test_clarify_needs_a_question_at_the_end_tools_optional(self):
        q = _q("clarify", allow_no_tool=True)
        asks = "先想一下。\n\n你比較想做出東西，還是弄懂原理？"
        picks = "A. 寫程式\nB. 碰硬體\n你回我 A / B，我再幫你縮小。"
        self.assertTrue(judge.hard_signals(q, _rec("X01", [], asks), BANNED, KNOWN)["behavior_ok"])
        self.assertTrue(judge.hard_signals(q, _rec("X01", [], picks), BANNED, KNOWN)["behavior_ok"])
        self.assertTrue(judge.hard_signals(q, _rec("X01", ["search_courses"], asks), BANNED, KNOWN)["behavior_ok"])
        self.assertFalse(judge.hard_signals(q, _rec("X01", [], "資工系很適合你。"), BANNED, KNOWN)["behavior_ok"])

    def test_question_mark_only_counts_near_the_end(self):
        q = _q("clarify", allow_no_tool=True)
        ans = "你喜歡什麼？\n" + "\n".join(f"第{i}點說明。" for i in range(8))
        self.assertFalse(judge.hard_signals(q, _rec("X01", [], ans), BANNED, KNOWN)["behavior_ok"])

    def test_correct_premise_needs_a_cue_and_a_lookup_unless_allowed(self):
        cue = "中大課程資料裡沒有法律系，但有相關的課。"
        q = _q("correct_premise")
        self.assertTrue(judge.hard_signals(q, _rec("X01", ["search_courses"], cue), BANNED, KNOWN)["behavior_ok"])
        no_lookup = judge.hard_signals(q, _rec("X01", [], cue), BANNED, KNOWN)
        self.assertFalse(no_lookup["behavior_ok"])
        self.assertIn("沒有先查證", no_lookup["behavior_problem"])
        free = _q("correct_premise", allow_no_tool=True)
        self.assertTrue(judge.hard_signals(free, _rec("X01", [], "薪水沒辦法保證，課程資料也沒有薪資統計。"), BANNED, KNOWN)["behavior_ok"])
        self.assertFalse(judge.hard_signals(q, _rec("X01", ["search_courses"], "資工系課很多，祝你順利。"), BANNED, KNOWN)["behavior_ok"])

    def test_premise_cues_cover_common_phrasings(self):
        for text in ("資工不是不用數學", "不是數學超強才能讀 AI", "其實需要不少數學", "無法保證你一定成為工程師"):
            self.assertTrue(judge.observe_behavior(_rec("X01", [], text), BANNED)["premise_cue"], text)

    def test_empty_or_error_is_never_correct(self):
        q = _q("clarify", allow_no_tool=True)
        self.assertFalse(judge.hard_signals(q, _rec("X01", [], ""), BANNED, KNOWN)["behavior_ok"])
        self.assertFalse(judge.hard_signals(q, _rec("X01", [], "你好？", error="boom"), BANNED, KNOWN)["behavior_ok"])

    def test_required_tool_subcheck_is_kept(self):
        q = next(q for q in EVAL["questions"] if q["tools"]["all"])
        self.assertFalse(judge.check_required_tools(q, _rec(q["id"], []), BANNED)["pass"])


class EvalSetLabels(unittest.TestCase):
    def test_every_question_has_a_valid_expected_behavior(self):
        for q in EVAL["questions"]:
            self.assertIn(q["expected_behavior"], judge.BEHAVIORS, q["id"])

    def test_hybrid_policy_examples_are_labelled_consistently(self):
        # 系統提示詞範例 B（A01）沒線索只追問；範例 B2（A03）有線索先查；範例 C（F04）查無系所
        self.assertEqual(QMAP["A01"]["expected_behavior"], "clarify")
        self.assertEqual(QMAP["A03"]["expected_behavior"], "query")
        self.assertEqual(QMAP["F04"]["expected_behavior"], "correct_premise")
        self.assertFalse(QMAP["F04"]["tools"]["allow_no_tool"])

    def test_error_flags_match_eval_set(self):
        self.assertEqual(set(judge.ERROR_FLAGS), set(EVAL["meta"]["error_flags"]))


class Judgement(unittest.TestCase):
    def test_parse_judgement_validates_checks_and_scores(self):
        good = _judgement()
        self.assertIsNotNone(judge.parse_judgement("前言\n" + json.dumps(good) + "\n以上 {x}", 2))
        self.assertIsNone(judge.parse_judgement(json.dumps(good), 3))  # 檢查點數量不符
        bad = _judgement(); bad["scores"]["honesty"] = 3
        self.assertIsNone(judge.parse_judgement(json.dumps(bad), 2))
        bad = _judgement(); bad["checks"][0]["verdict"] = "partly"
        self.assertIsNone(judge.parse_judgement(json.dumps(bad), 2))
        self.assertIsNone(judge.parse_judgement("不是 json", 2))

    def test_parse_judgement_drops_invented_flags_and_normalises_types(self):
        j = _judgement(flags=["hallucinated_course", "overwhelming_list"])
        j["needs_human_check"] = "一句字串"
        j["behavior"] = "oops"
        got = judge.parse_judgement(json.dumps(j), 2)
        self.assertEqual(got["flags"], ["hallucinated_course"])
        self.assertEqual(got["needs_human_check"], ["一句字串"])
        self.assertEqual(got["behavior"], {"asks_question": False, "corrects_premise": False})

    def test_prompt_includes_tool_data_and_its_limitation(self):
        q = QMAP["B03"]
        rec = _rec("B03", ["get_dept_overview"])
        p = judge.build_prompt(q, rec, judge.hard_signals(q, rec, BANNED, KNOWN))
        self.assertIn("get_dept_overview({}) → 3 筆：資料結構", p)
        self.assertIn("沒有課程描述", p)
        self.assertIn("1. " + q["checks"][0], p)

    def test_prompt_lists_departments_when_available(self):
        q = QMAP["F04"]
        rec = _rec("F04", ["search_courses"])
        p = judge.build_prompt(q, rec, judge.hard_signals(q, rec, BANNED, KNOWN), ["法律與政府研究所碩士班", "資訊工程學系"])
        self.assertIn("法律與政府研究所碩士班、資訊工程學系", p)

    def test_tool_data_is_truncated(self):
        rec = {"tool_calls": [{"tool": "search_courses", "args": {"q": "x"}, "count": 99,
                               "coursesFound": [f"課程{i:03d}" for i in range(99)]}] * 20}
        lines = judge.format_tool_data(rec)
        self.assertLessEqual(sum(map(len, lines)), judge.TOOL_DATA_CHARS + 200)
        self.assertIn("另有", lines[0])
        self.assertIn("省略", lines[-1])

    def test_default_judge_model_is_a_pinned_version_not_an_alias(self):
        self.assertEqual(judge.DEFAULT_JUDGE_MODEL, "claude-sonnet-5-5")


class Summary(unittest.TestCase):
    def _rows(self):
        q = _q("query")
        long_ans = "<course>資料結構</course>" + "字" * 1000
        return [
            _row("X01", q, _rec("X01", ["search_courses"], long_ans, elapsed=10),
                 [_judgement(2, ("met", "met")), _judgement(2, ("met", "met"))]),
            _row("X02", q, _rec("X02", [], "<course>量子美食學</course>", elapsed=20),
                 [_judgement(1, ("met", "not_met"), ["hallucinated_course"]), _judgement(0, ("not_met", "not_met"))]),
            _row("X03", _q("clarify", True), _rec("X03", [], "你想先看哪一類？", elapsed=30)),
        ]

    def test_summary_counts_hard_metrics(self):
        h = judge.summarize(self._rows())["hard"]
        self.assertEqual((h["course_tags"], h["course_found"], h["course_real_rate"]), (2, 1, 50.0))
        self.assertEqual((h["behavior_ok"], h["behavior_rate"]), (2, 66.7))
        self.assertEqual(h["behavior_by_type"]["clarify"], {"n": 1, "ok": 1})
        self.assertEqual((h["too_long"], h["median_elapsed_sec"]), (1, 20))

    def test_summary_ai_and_reliability(self):
        s = judge.summarize(self._rows())
        ai, rel = s["ai"], s["reliability"]
        self.assertEqual(ai["judgements"], 4)
        self.assertEqual(ai["check_rate"], 62.5)          # 5/8 個檢查點
        self.assertEqual(ai["aux_total"], 5.0)            # (8+8+4+0)/4
        self.assertEqual(ai["flags_any_pass"], {"hallucinated_course": 1})
        self.assertEqual(ai["flags_all_passes"], {})
        self.assertEqual(rel["paired_questions"], 2)
        self.assertEqual((rel["aux_exact"], rel["aux_within_1"]), (50.0, 50.0))
        self.assertEqual(rel["check_agree"], 75.0)        # 3/4 個檢查點判定一致
        self.assertEqual([d["key"] for d in rel["disagreements"]], ["X02"])

    def test_report_has_three_layers_and_names_the_model(self):
        meta = {"run_id": "r", "results_file": "r.json", "eval_file": "e.json",
                "model": judge.DEFAULT_JUDGE_MODEL, "passes": 2, "no_judge": False}
        text = judge.build_report(self._rows(), meta, EVAL["meta"]["groups"])
        for part in ("第一層", "第二層", "第三層", "量子美食學", "`claude-sonnet-5-5` ×4", "X03"):
            self.assertIn(part, text)
        self.assertNotIn("混用了多個評審模型", text)

    def test_report_without_judge_only_has_hard_metrics(self):
        meta = {"run_id": "r", "results_file": "r.json", "eval_file": "e.json",
                "model": judge.DEFAULT_JUDGE_MODEL, "passes": 1, "no_judge": True}
        rows = [dict(r, judgements=[], judge_models=[]) for r in self._rows()]
        text = judge.build_report(rows, meta, EVAL["meta"]["groups"])
        self.assertIn("第一層", text)
        self.assertNotIn("第二層", text)
        self.assertNotIn("未完成評審", text)

    def test_repeat_runs_get_distinct_keys(self):
        keys = [k for k, _ in judge.index_records([_rec("A01", []), _rec("A01", []), _rec("B01", [])])]
        self.assertEqual(keys, ["A01", "A01#2", "B01"])


if __name__ == "__main__":
    unittest.main()
