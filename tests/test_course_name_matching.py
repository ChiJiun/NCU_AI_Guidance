import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services import graph_service  # noqa: E402


class ExactNameFirst(unittest.TestCase):
    def test_exact_name_excludes_substring_and_closed_courses(self):
        # 回歸：查「演算法」曾連《數位訊號處理演算法》《生物資訊演算法》（已停開）的概念一起合併
        names = {c["name"] for c in graph_service.get_course_info_exact_first("演算法")}
        self.assertEqual(names, {"演算法"})

    def test_falls_back_to_fuzzy_when_no_exact_match(self):
        fuzzy = graph_service.get_course_info("深度學習")
        self.assertTrue(fuzzy)
        got = graph_service.get_course_info_exact_first("深度學")  # 沒有剛好叫這個名字的課
        self.assertTrue(got)

    def test_knowledge_map_lists_each_department_once(self):
        km = graph_service.get_course_knowledge_map("演算法")
        depts = [c["dept"] for c in km["same_name_courses"]]
        self.assertEqual(len(depts), len(set(depts)))
        self.assertGreaterEqual(len(depts), 3)
        self.assertNotIn("Z轉換", {c["name"] for c in km["concepts"]})


if __name__ == "__main__":
    unittest.main()
