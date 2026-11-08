import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services import llm_service as llm  # noqa: E402

KNOWLEDGE_MAP = """【演算法】（生醫科學與工程學系，3學分）

使用技術：Python, C++
涵蓋概念（共 92 個）：AVL樹, NP完備性, 分治法

概念重疊最高的相關課程（可延伸學習）：
  - 資料結構（生醫科學與工程學系） [共享 2.5 個概念]
  - 演算法Ｉ（數學系）
"""


class KnowledgeMapPool(unittest.TestCase):
    def test_queried_course_itself_enters_the_pool(self):
        # 回歸：被查詢的課在標題行，過去只解析清單行，導致回答標了 <course> 卻沒有卡片
        names = {(c["name"], c["dept"]) for c in llm._parse_courses_from_str("get_course_knowledge_map", KNOWLEDGE_MAP)}
        self.assertIn(("演算法", "生醫科學與工程學系"), names)
        self.assertIn(("資料結構", "生醫科學與工程學系"), names)
        self.assertIn(("演算法Ｉ", "數學系"), names)

    def test_header_credits_are_kept(self):
        first = llm._parse_courses_from_str("get_course_knowledge_map", KNOWLEDGE_MAP)[0]
        self.assertEqual((first["name"], first["credits"]), ("演算法", 3))

    def test_same_name_courses_from_other_depts_are_listed(self):
        text = (KNOWLEDGE_MAP.split("\n\n")[0]
                + "\n另有同名課程：演算法（資訊管理學系，3學分）、演算法（通訊工程學系，3學分）\n"
                + "（以下概念與技術是這些同名課程合併的結果）\n\n" + KNOWLEDGE_MAP.split("\n\n", 1)[1])
        got = {(c["name"], c["dept"]) for c in llm._parse_courses_from_str("get_course_knowledge_map", text)}
        for dept in ("生醫科學與工程學系", "資訊管理學系", "通訊工程學系"):
            self.assertIn(("演算法", dept), got)

    def test_pool_keeps_same_name_courses_from_different_depts(self):
        text = ("【演算法】（生醫科學與工程學系，3學分）\n另有同名課程：演算法（資訊管理學系，3學分）\n\n"
                "概念重疊最高的相關課程（可延伸學習）：\n  - 資料結構（生醫科學與工程學系）\n")
        pool: dict = {}
        llm._collect_course_pool("get_course_knowledge_map", text, pool)
        again = dict(pool)
        llm._collect_course_pool("get_course_knowledge_map", text, pool)   # 重複收集不應產生重複卡片
        self.assertEqual(len(pool), len(again))
        algo_depts = {v["dept"] for v in pool.values() if v["name"] == "演算法"}
        self.assertEqual(algo_depts, {"生醫科學與工程學系", "資訊管理學系"})

    def test_find_similar_courses_has_no_header_course(self):
        text = "與「線性代數」概念相近的課程（共 1 門）：\n- 應用數學（大氣科學學系，3學分） [共享概念：2.0 個]"
        names = [c["name"] for c in llm._parse_courses_from_str("find_similar_courses", text)]
        self.assertEqual(names, ["應用數學"])


class PoolCoverageForAllCourseTools(unittest.TestCase):
    """回歸：評測 100 題中有 62 個真實課名被回答點名卻沒有卡片，來源是這幾個工具沒有被收進課程池。"""

    def test_concept_neighborhood_output_enters_the_pool(self):
        text = ("以「機率」為中心的概念鄰域（2 跳，共 3 門課）：\n"
                "- 機率（通訊工程學系，3 學分）\n"
                "- 機率論（數學系，3 學分）\n"
                "- 隨機程序概論 [已停開]（通訊工程學系，3 學分）\n")
        pool: dict = {}
        llm._collect_course_pool("explore_concept_neighborhood", text, pool)
        got = {(v["name"], v["dept"], v["credits"]) for v in pool.values()}
        self.assertEqual(got, {("機率", "通訊工程學系", 3), ("機率論", "數學系", 3)})  # 已停開的不收

    def test_credits_with_a_space_are_parsed(self):
        got = llm._parse_courses_from_str("explore_concept_neighborhood", "- 統計學（管理學院，3 學分）")
        self.assertEqual([(c["name"], c["credits"]) for c in got], [("統計學", 3)])

    def test_dept_overview_elective_examples_enter_the_pool(self):
        result = {"found": True, "dept_name": "中國文學系", "required_courses": [{"name": "文字學", "credits": 3}],
                  "elective_by_domain": [{"domain": "古典文學", "courses": 9, "examples": ["詩三百選", "戲劇選"]}]}
        pool: dict = {}
        llm._collect_course_pool("get_dept_overview", result, pool)
        by_name = {v["name"]: v for v in pool.values()}
        self.assertEqual(set(by_name), {"文字學", "詩三百選", "戲劇選"})
        self.assertEqual(by_name["戲劇選"]["type"], "選修")
        self.assertEqual(by_name["文字學"]["type"], "必修")


class CollapseRepeatedAnswer(unittest.TestCase):
    def test_identical_answer_written_twice_is_collapsed(self):
        one = "可以呀。\n\n你比較偏哪一種？\n- 做東西\n- 寫程式"
        self.assertEqual(llm._collapse_repeated_answer(one + "\n\n" + one), one)

    def test_repeat_with_only_whitespace_differences_is_collapsed(self):
        a = "你這個方向很適合先分兩條看。\n\n1. 偏儀器\n2. 偏資料分析"
        b = "你這個方向很適合先分兩條看。 \n\n1. 偏儀器  \n2. 偏資料分析"
        self.assertEqual(llm._collapse_repeated_answer(a + "\n\n" + b), a)

    def test_normal_answers_are_untouched(self):
        # 同一門課在不同小節各列一次是正常內容，不能被誤刪
        text = "基礎：\n- <course>自然語言處理</course>\n\n進階：\n- <course>自然語言處理</course>\n- 深度學習"
        self.assertEqual(llm._collapse_repeated_answer(text), text)
        self.assertEqual(llm._collapse_repeated_answer("好"), "好")
        short = "短答\n\n短答"  # 少於 30 字不處理
        self.assertEqual(llm._collapse_repeated_answer(short), short)


if __name__ == "__main__":
    unittest.main()
