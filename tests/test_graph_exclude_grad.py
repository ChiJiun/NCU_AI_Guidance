import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services import graph_service  # noqa: E402


def _levels(names_or_ids):
    g = graph_service._g()
    by_id = g["nodes"]
    return {by_id[i].get("level") for i in names_or_ids if i in by_id}


class ExcludeGradCourses(unittest.TestCase):
    def test_ppr_explore_hides_grad_courses_when_asked(self):
        res = graph_service.ppr_explore(["線性代數"], top_k=15, node_type_filter=["Course"], exclude_grad=True)
        self.assertTrue(res)
        self.assertNotIn("grad", _levels(r["id"] for r in res))

    def test_ppr_explore_keeps_default_behaviour(self):
        # 預設不過濾，避免影響其他呼叫端；至少要有結果
        res = graph_service.ppr_explore(["機器學習"], top_k=15, node_type_filter=["Course"])
        self.assertTrue(res)

    def test_concept_neighborhood_hides_grad_courses_when_asked(self):
        res = graph_service.explore_by_concept_neighborhood("機器學習", top_k=15, exclude_grad=True)
        if res:  # 沒有向量入口時可能為空，這裡只檢查有結果時不含研究所課
            self.assertNotIn("grad", _levels(r["id"] for r in res))

    def test_is_grad_course_only_marks_grad_courses(self):
        self.assertTrue(graph_service._is_grad_course({"node_type": "Course", "level": "grad"}))
        self.assertFalse(graph_service._is_grad_course({"node_type": "Course", "level": "ugrad"}))
        self.assertFalse(graph_service._is_grad_course({"node_type": "Course", "level": "unknown"}))
        self.assertFalse(graph_service._is_grad_course({"node_type": "Instructor", "level": "grad"}))


if __name__ == "__main__":
    unittest.main()
