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
        for heading in ("## 一、不可違反的原則（防止幻覺）", "## 二、怎麼回答高中生"):
            self.assertIn(heading, self.prompt)
        for phrase in ("薪資", "錄取分數", "視為查無", "114 學年", "不編造網址"):
            self.assertIn(phrase, self.prompt)

    def test_concepts_and_technologies_are_not_course_tags(self):
        # 回歸：模型曾把「二元搜尋樹」「C++」這類概念與技術也用 <course> 包起來
        self.assertIn("概念」與「技術」", self.prompt)
        self.assertIn("不是課程", self.prompt)
        self.assertIn("老師姓名、系所名稱、學分學程名稱同樣不是課程", self.prompt)

    def test_explore_and_clarify_rules_do_not_overlap(self):
        # 「探索」與「先追問」兩條規則曾同時適用於「我不知道喜歡什麼」，導致模型把兩種回答都寫出來
        self.assertIn("不呼叫工具，也不要同時列出路徑與課程", self.prompt)
        self.assertIn("同一則回答不要把相同內容換句話再寫一遍", self.prompt)

    def test_hybrid_clarification_policy(self):
        # 有線索先查再問、沒線索才只問、事實性問題一律查證（評測中純追問會讓學生拿不到任何系所或課程）
        for phrase in ("有線索 → 先查再答，最後只問一個問題", "完全沒線索 → 只問不查", "事實性問題一律查證，不憑印象"):
            self.assertIn(phrase, self.prompt)
        self.assertIn("範例 B2 — 有線索，先查再問", self.prompt)

    def test_examples_cover_compare_clarify_and_missing_department(self):
        for title in ("範例 A — 比較系所", "範例 B — 資訊太少，先問不查", "範例 C — 查無系所"):
            self.assertIn(title, self.prompt)

    def test_length_limits_are_stated_as_numbers(self):
        # 評測中 30% 的回答被評為一次列太多，規則要寫成可檢查的數字而不是「適中」
        self.assertIn("約 500 字內", self.prompt)
        self.assertIn("最多 3–4 條路徑", self.prompt)

    def test_prompt_stays_slim(self):
        # 規則過多會稀釋指令遵循；system prompt 超過 4500 tokens 就該重新審視
        import tiktoken
        self.assertLess(len(tiktoken.get_encoding("o200k_base").encode(self.prompt)), 4500)


if __name__ == "__main__":
    unittest.main()
