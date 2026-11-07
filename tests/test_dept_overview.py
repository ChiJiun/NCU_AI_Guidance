import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import graph_service  # noqa: E402

TOOLS_PATH = ROOT / "backend" / "app" / "services" / "tools.py"


class DeptOverviewDataTests(unittest.TestCase):
    def test_all_required_courses_are_listed_without_truncation(self):
        raw = graph_service.get_dept_required_courses("中國文學系")
        overview = graph_service.get_dept_overview("中國文學系")
        listed_ids = {i for c in overview["required_courses"] for i in c["course_ids"]}
        self.assertEqual({c["id"] for c in raw}, listed_ids)

    def test_same_name_semesters_are_merged(self):
        overview = graph_service.get_dept_overview("中國文學系")
        names = [c["name"] for c in overview["required_courses"]]
        self.assertEqual(len(names), len(set(names)))

    def test_summary_lists_respect_configured_limits(self):
        for dept in ("資訊工程學系", "機械工程學系", "中國文學系"):
            o = graph_service.get_dept_overview(dept)
            self.assertLessEqual(len(o["course_domains"]), graph_service.OVERVIEW_TOP_DOMAINS)
            self.assertLessEqual(len(o["topic_fields"]), graph_service.OVERVIEW_TOP_FIELDS)
            self.assertLessEqual(len(o["technologies"]), graph_service.OVERVIEW_TOP_TECHNOLOGIES)
            self.assertLessEqual(len(o["core_competencies"]), graph_service.OVERVIEW_TOP_COMPETENCIES)
            self.assertLessEqual(len(o["elective_by_domain"]), graph_service.OVERVIEW_TOP_ELECTIVE_GROUPS)

    def test_generic_domains_and_common_course_competencies_are_excluded(self):
        o = graph_service.get_dept_overview("資訊工程學系")
        domains = {d["domain"] for d in o["course_domains"]}
        self.assertFalse(domains & graph_service._GENERIC_DOMAINS)
        competencies = {c["name"] for c in o["core_competencies"]}
        self.assertNotIn("發掘問題", competencies)  # 只來自微積分的共同課標籤

    def test_minimum_support_filters_single_course_technologies(self):
        o = graph_service.get_dept_overview("中國文學系")
        self.assertEqual([], o["technologies"])  # MBTI 等只出現在單一課程

    def test_groups_split_common_and_track_courses(self):
        o = graph_service.get_dept_overview("機械工程學系")
        self.assertNotIn("required_courses", o)
        common = {c["name"] for c in o["common_required_courses"]}
        self.assertEqual(3, len(o["tracks"]))
        for track in o["tracks"]:
            specific = {c["name"] for c in track["track_required_courses"]}
            self.assertFalse(common & specific)
            self.assertGreater(track["dept_required_credits"], 0)
            self.assertEqual(134, track["graduation"]["min_credits"])

    def test_elective_credit_rule_is_exposed_when_no_course_list(self):
        o = graph_service.get_dept_overview("資訊工程學系")
        self.assertEqual(21, o["elective_rules"][0]["select_credits"])

    def test_ambiguous_or_unknown_names_do_not_guess(self):
        unknown = graph_service.get_dept_overview("不存在系")
        self.assertFalse(unknown["found"])
        ambiguous = graph_service.get_dept_overview("工程")
        self.assertFalse(ambiguous["found"])
        self.assertTrue(ambiguous["fallback_candidates"])

    def test_no_teacher_personal_data_in_overview(self):
        o = graph_service.get_dept_overview("資訊工程學系")
        self.assertNotIn("research_topics", o)
        self.assertNotIn("faculty_count", o)

    def test_stats_only_use_114_bachelor_outline_and_skip_closed_courses(self):
        index = graph_service._outline_index()
        offered = graph_service._offered_codes("資訊工程學系")
        self.assertTrue(offered)
        for code in offered:
            self.assertEqual(graph_service.OVERVIEW_PROGRAM, index[code]["program"])
            self.assertFalse(index[code]["closed"])
            self.assertEqual("資訊工程學系", index[code]["unit"])

    def test_common_course_units_are_not_counted_as_department_courses(self):
        index = graph_service._outline_index()
        for code in graph_service._offered_codes("企業管理學系"):
            self.assertEqual("企業管理學系", index[code]["unit"])

    def test_graduation_info_comes_from_curriculum_requirements(self):
        o = graph_service.get_dept_overview("資訊工程學系")
        self.assertEqual(128, o["graduation"]["min_credits"])
        self.assertEqual(83, o["graduation"]["required_credits_including_common"])
        self.assertLess(o["dept_required_credits"], o["graduation"]["required_credits_including_common"])
        self.assertIn("required_credits_note", o)

    def test_courses_without_outline_are_flagged_not_counted(self):
        o = graph_service.get_dept_overview("企業管理學系")
        self.assertIn("策略管理", o["stats_basis"]["required_without_outline"])
        flagged = [c for c in o["required_courses"] if not c["outline_available"]]
        self.assertTrue(any(c["name"] == "策略管理" for c in flagged))

    def test_sources_distinguish_syllabus_fields_from_system_analysis(self):
        sources = graph_service.get_dept_overview("資訊工程學系")["sources"]
        self.assertIn("課程綱要", sources["course_domains"])
        self.assertIn("課程綱要", sources["core_competencies"])
        self.assertIn("衍生內容", sources["topic_fields"])
        self.assertIn("衍生內容", sources["technologies"])

    def test_limited_data_units_warn(self):
        o = graph_service.get_dept_overview("資訊電機學院學士班")
        self.assertTrue(o["stats_basis"]["courses_counted"] >= 0)
        if o["stats_basis"]["courses_counted"] < graph_service.OVERVIEW_MIN_COURSES_FOR_STATS:
            self.assertIn("stats_warning", o)

    def test_alias_resolves(self):
        self.assertEqual("資訊工程學系", graph_service.get_dept_overview("資工系")["dept_name"])


class DeptOverviewWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(TOOLS_PATH.read_text(encoding="utf-8"))

    def _strings(self, assign_name):
        node = next(
            n.value for n in self.tree.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == assign_name for t in n.targets)
        )
        return {c.value for c in ast.walk(node) if isinstance(c, ast.Constant) and isinstance(c.value, str)}

    def test_tool_is_registered_and_advertised(self):
        self.assertIn("get_dept_overview", self._strings("_TOOL_MAP"))
        self.assertIn("get_dept_overview", self._strings("TOOLS"))

    def test_overview_does_not_touch_department_vectors(self):
        fn = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == "tool_get_dept_overview")
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
        self.assertNotIn("retriever", names)


if __name__ == "__main__":
    unittest.main()
