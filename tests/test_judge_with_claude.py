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


def _rec(qid, tools, answer="", cards=()):
    return {"category": qid, "answer": answer, "error": "", "tools_used": list(tools),
            "tool_calls": [{"tool": t, "args": {}} for t in tools],
            "course_cards": [{"name": c} for c in cards]}


class JudgeChecks(unittest.TestCase):
    def test_every_question_has_a_passing_shape(self):
        # 對每題用「預期的工具」造一筆紀錄，程式檢查都應該通過
        for q in EVAL["questions"]:
            t = q["tools"]
            tools = list(t["all"]) + (list(t["any"][:1]) if t["any"] else [])
            tools += [n for n, c in t["min_calls"].items() for _ in range(c - 1)]
            res = judge.check_tools(q, _rec(q["id"], tools), BANNED)
            self.assertTrue(res["pass"], (q["id"], res))

    def test_missing_required_tool_fails(self):
        q = next(q for q in EVAL["questions"] if q["tools"]["all"])
        res = judge.check_tools(q, _rec(q["id"], []), BANNED)
        self.assertFalse(res["pass"])

    def test_tag_without_card_is_reported(self):
        rec = _rec("X", [], "推薦<course>資料結構（資工系）</course>和<course>量子美食學</course>", ["資料結構"])
        self.assertEqual(judge.check_course_tags(rec)["tag_without_card"], ["量子美食學"])

    def test_parse_judgement(self):
        good = {"scores": {k: 1 for k in judge.DIMENSIONS}, "reasons": {}, "flags": []}
        self.assertIsNotNone(judge.parse_judgement("前言\n" + json.dumps(good) + "\n"))
        bad = {"scores": {**good["scores"], "evidence": 3}}
        self.assertIsNone(judge.parse_judgement(json.dumps(bad)))
        self.assertIsNone(judge.parse_judgement("不是 json"))

    def test_parse_judgement_drops_invented_flags_and_normalises_types(self):
        j = {"scores": {k: 2 for k in judge.DIMENSIONS}, "flags": ["overwhelming_list", "made_up_flag"],
             "needs_human_check": "只是一句字串"}
        got = judge.parse_judgement(json.dumps(j))
        self.assertEqual(got["flags"], ["overwhelming_list"])
        self.assertEqual(got["needs_human_check"], ["只是一句字串"])
        self.assertEqual(judge.parse_judgement(json.dumps({**j, "flags": "oops"}))["flags"], [])

    def test_parse_judgement_ignores_trailing_text_with_braces(self):
        good = {"scores": {k: 1 for k in judge.DIMENSIONS}, "reasons": {}, "flags": []}
        text = json.dumps(good, ensure_ascii=False) + '\n\n以上是依標準 {scores} 評分的結果。'
        self.assertIsNotNone(judge.parse_judgement(text))
        self.assertIsNone(judge.parse_judgement('["不是物件"]'))

    def test_default_judge_model_is_a_pinned_version_not_an_alias(self):
        # 別名（sonnet）會隨 Claude Code 更新而指向不同版本，會讓不同次的評分無法比較
        self.assertEqual(judge.DEFAULT_JUDGE_MODEL, "claude-sonnet-5-5")

    def _judged_row(self, model):
        q = EVAL["questions"][0]
        rec = _rec(q["id"], [], "回答")
        scores = {k: 1 for k in judge.DIMENSIONS}
        return {"key": q["id"], "group": q["group"], "question": q["question"], "error": "",
                "signals": judge.signals(q, rec, BANNED),
                "judgement": {"scores": scores, "reasons": {}, "flags": [], "needs_human_check": []},
                "judge_model": model}

    def test_report_names_the_judge_model_actually_used(self):
        meta = {"run_id": "r", "results_file": "r.json", "model": judge.DEFAULT_JUDGE_MODEL}
        text = judge.build_report([self._judged_row("claude-sonnet-5-5")], meta, EVAL["meta"]["groups"])
        self.assertIn("實際使用的評審模型：`claude-sonnet-5-5` ×1", text)
        self.assertNotIn("混用了多個評審模型", text)

    def test_report_warns_when_models_are_mixed_or_unrecorded(self):
        meta = {"run_id": "r", "results_file": "r.json", "model": judge.DEFAULT_JUDGE_MODEL}
        rows = [self._judged_row("claude-sonnet-5-5"), self._judged_row("")]
        text = judge.build_report(rows, meta, EVAL["meta"]["groups"])
        self.assertIn("混用了多個評審模型", text)
        self.assertIn("（未記錄）", text)

    def test_error_flags_match_eval_set(self):
        self.assertEqual(set(judge.ERROR_FLAGS), set(EVAL["meta"]["error_flags"]))

    def test_repeat_runs_get_distinct_keys(self):
        keys = [k for k, _ in judge.index_records([_rec("A01", []), _rec("A01", []), _rec("B01", [])])]
        self.assertEqual(keys, ["A01", "A01#2", "B01"])


if __name__ == "__main__":
    unittest.main()
