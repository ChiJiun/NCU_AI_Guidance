import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

LLM_SERVICE = ROOT / "backend" / "app" / "services" / "llm_service.py"
TOOLS = ROOT / "backend" / "app" / "services" / "tools.py"


def _constant(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        n.value for n in tree.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
    )


def _advertised_tool_names() -> set[str]:
    tools_list = _constant(TOOLS, "TOOLS")
    names = set()
    for node in ast.walk(tools_list):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "name" and isinstance(v, ast.Constant):
                    names.add(v.value)
    return names


class SystemPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prompt = _constant(LLM_SERVICE, "SYSTEM_PROMPT").value
        cls.tools = _advertised_tool_names()

    def test_prompt_only_names_tools_that_exist(self):
        used = set(re.findall(r"\b((?:get|search|find|ppr|explore)_[a-z_]+)", self.prompt))
        self.assertEqual(set(), used - self.tools)

    def test_every_advertised_tool_has_guidance(self):
        missing = {t for t in self.tools if t not in self.prompt}
        self.assertEqual(set(), missing)

    def test_disabled_department_info_is_not_mentioned(self):
        self.assertNotIn("get_dept_info", self.prompt)

    def test_competency_scale_matches_data(self):
        self.assertNotIn("level_num 1–4", self.prompt)
        self.assertIn("0–5", self.prompt)

    def test_no_internal_wording_is_scripted_for_users(self):
        self.assertNotIn("圖中此領域", self.prompt)

    def test_no_real_person_name_in_examples(self):
        self.assertNotIn("張家凱", self.prompt)

    def test_anti_hallucination_and_audience_sections_exist(self):
        for heading in ("## 不確定性與禁止項（防止幻覺）", "## 對高中生的說明方式"):
            self.assertIn(heading, self.prompt)
        for phrase in ("薪資", "錄取分數", "視為查無", "114 學年", "不編造網址"):
            self.assertIn(phrase, self.prompt)

    def test_examples_cover_compare_clarify_and_missing_department(self):
        for title in ("範例 13", "範例 14", "範例 15"):
            self.assertIn(title, self.prompt)


if __name__ == "__main__":
    unittest.main()
