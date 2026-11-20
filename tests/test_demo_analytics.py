"""示範學生個人分析：純計算函式與正式版共用，這裡驗證計算結果。"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.session_store import compute_course_analytics, compute_pdf_analytics  # noqa: E402

COLLEGES = {"大氣科學學系": "地球科學學院", "資訊管理學系": "管理學院"}


class CourseAnalyticsTest(unittest.TestCase):
    def test_counts_turns_courses_and_colleges(self):
        cards = [
            {"code": "AP1001", "name": "大氣科學概論", "dept": "大氣科學學系", "domain_tags": "大氣科學::0.9"},
            {"code": "IM1013", "name": "初階程式設計", "dept": "資訊管理學系", "domain_tags": "程式::0.3"},
        ]
        rows = [
            {"tools_used": ["search_courses"], "course_pool": cards, "course_cards": cards},
            {"tools_used": ["search_courses"], "course_pool": cards[:1], "course_cards": cards[:1]},
        ]
        result = compute_course_analytics(rows, total_sessions=1, college_map=COLLEGES)
        self.assertEqual(result["overview"]["total_turns"], 2)
        self.assertEqual(result["overview"]["total_courses_explored"], 2)
        self.assertEqual(result["overview"]["fav_college"], "地球科學學院")
        self.assertEqual(result["tool_usage"][0]["count"], 2)
        # 低於 0.5 的興趣標籤不計入
        self.assertEqual([t["tag"] for t in result["top_domain_tags"]], ["大氣科學"])


class PdfAnalyticsTest(unittest.TestCase):
    def test_depth_and_cross_college_type(self):
        t = datetime(2026, 11, 17, tzinfo=timezone.utc)
        convs = [
            {"thread_id": "a", "document_id": 1, "created_at": t},
            {"thread_id": "b", "document_id": 2, "created_at": t},
            {"thread_id": "c", "document_id": 3, "created_at": t},
        ]
        meta = {
            1: {"title": "A", "department": "大氣科學學系", "year": "107"},
            2: {"title": "B", "department": "資訊管理學系", "year": "108"},
            3: {"title": "C", "department": "中國文學系", "year": "109"},
        }
        colleges = {**COLLEGES, "中國文學系": "文學院"}
        recent = [{"thread_id": "a", "user_question": "q", "created_at": t}]
        result = compute_pdf_analytics(convs, {"a": 2, "b": 2, "c": 2}, recent, meta, colleges)
        self.assertEqual(result["overview"]["total_questions"], 6)
        self.assertEqual(result["overview"]["avg_depth"], 2.0)
        self.assertEqual(result["exploration_type"]["type"], "跨域探索型")
        self.assertEqual(result["recent_questions"][0]["document_title"], "A")


if __name__ == "__main__":
    unittest.main()
