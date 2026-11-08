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


if __name__ == "__main__":
    unittest.main()
