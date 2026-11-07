import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "test_course_agent"))

import render_eval_set  # noqa: E402


class EvalSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = render_eval_set.load()

    def test_dataset_passes_validation(self):
        self.assertEqual([], render_eval_set.validate(self.data))

    def test_every_enabled_tool_is_forced_by_some_question(self):
        forced = {t for q in self.data["questions"] for t in q["tools"]["all"]}
        self.assertEqual(set(self.data["meta"]["tools_enabled"]), forced)

    def test_enabled_tools_match_agent_schema(self):
        import ast
        tree = ast.parse((ROOT / "backend" / "app" / "services" / "tools.py").read_text(encoding="utf-8"))
        tool_map = next(
            n.value for n in tree.body
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_TOOL_MAP" for t in n.targets)
        )
        advertised = {k.value for k in tool_map.keys if isinstance(k, ast.Constant)}
        for name in self.data["meta"]["tools_enabled"]:
            self.assertIn(name, advertised)

    def test_has_enough_multi_tool_and_clarification_questions(self):
        qs = self.data["questions"]
        self.assertGreaterEqual(sum(q["tools"]["multi_tool"] for q in qs), 15)
        self.assertGreaterEqual(sum("追問" in q["intent"] for q in qs), 15)
        self.assertGreaterEqual(sum("邊界" in q["intent"] for q in qs), 10)

    def test_generated_files_are_up_to_date(self):
        self.assertEqual(render_eval_set.MD_PATH.read_text(encoding="utf-8"), render_eval_set.render_md(self.data))
        self.assertEqual(render_eval_set.TXT_PATH.read_text(encoding="utf-8"), render_eval_set.render_txt(self.data))


if __name__ == "__main__":
    unittest.main()
