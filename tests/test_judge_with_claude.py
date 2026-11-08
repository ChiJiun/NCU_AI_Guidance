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

    def test_repeat_runs_get_distinct_keys(self):
        keys = [k for k, _ in judge.index_records([_rec("A01", []), _rec("A01", []), _rec("B01", [])])]
        self.assertEqual(keys, ["A01", "A01#2", "B01"])


if __name__ == "__main__":
    unittest.main()
