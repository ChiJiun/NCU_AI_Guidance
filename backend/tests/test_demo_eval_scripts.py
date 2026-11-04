"""Demo 錄製、案例驗證、評估題組與評分統計腳本的測試（純函式，不需網路／AWS）。"""
import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


runner = _load("assistant_runner", "scripts/demo/assistant_runner.py")
record = _load("record_demo_cases", "scripts/demo/record_demo_cases.py")
validate = _load("validate_demo_cases", "scripts/demo/validate_demo_cases.py")
build_ts = _load("build_test_set", "scripts/evaluation/build_test_set.py")
sheet = _load("make_score_sheet", "scripts/evaluation/make_score_sheet.py")
analyze = _load("analyze_scores", "scripts/evaluation/analyze_scores.py")


# ── SSE 解析 ────────────────────────────────────────────────────────────────

def test_parse_sse_lines_skips_noise():
    lines = ["", ": comment", "data: {\"a\": 1}", b"data: {\"b\": 2}", "data: not-json", "data: [1,2]"]
    assert runner.parse_sse_lines(lines) == [{"a": 1}, {"b": 2}]


def test_build_course_turn_pairs_tools_and_verify():
    events = [
        {"type": "tool_start", "tool": "search_courses", "args": {"q": "AI"}},
        {"type": "token", "text": "部分"},
        {"type": "tool_done", "tool": "search_courses", "count": 7, "courses_found": ["機器學習"]},
        {"type": "verify_start", "pool_size": 7},
        {"type": "verify_done", "selected": ["機器學習"], "filtered_out": ["國文"], "method": "tag"},
        {"type": "done", "final_answer": "完整回答", "tools_used": ["search_courses"], "session_id": "s1",
         "course_cards": [{"name": "機器學習"}], "model": "m", "input_tokens": 3, "output_tokens": 4},
    ]
    turn = runner.build_course_turn("問題", events, 1234)
    assert turn["assistant"] == "完整回答"
    assert turn["error"] is None
    tool, verify = turn["steps"]
    assert tool == {"kind": "tool", "tool": "search_courses", "args": {"q": "AI"}, "status": "done",
                    "count": 7, "courses_found": ["機器學習"]}
    assert verify["selected"] == ["機器學習"] and verify["method"] == "tag"
    assert turn["session_id"] == "s1" and turn["latency_ms"] == 1234


def test_build_course_turn_without_done_is_error():
    turn = runner.build_course_turn("q", [{"type": "token", "text": "x"}], 1)
    assert turn["error"] and turn["assistant"] == "x"


def test_build_course_turn_error_event():
    turn = runner.build_course_turn("q", [{"type": "error", "message": "boom"}], 1)
    assert turn["error"] == "boom"


def test_build_research_turn():
    events = [
        {"session_id": "t1"},
        {"heartbeat": True},
        {"type": "agent_start", "agent": "retrieval", "label": "搜尋文獻"},
        {"type": "stage", "text": "檢索"},
        {"type": "stage", "text": "檢索"},
        {"token": "草稿"},
        {"replace": "最終回答", "sources": ["p.3"]},
        {"done": True, "session_id": "t1", "sources": ["p.3", "p.5"], "cancelled": False},
    ]
    turn = runner.build_research_turn("問", events, 9)
    assert turn["assistant"] == "最終回答"
    assert turn["stages"] == ["檢索"]
    assert turn["agent"] == {"name": "retrieval", "label": "搜尋文獻"}
    assert turn["sources"] == ["p.3", "p.5"]
    assert turn["thread_id"] == "t1" and turn["error"] is None


def test_build_research_turn_rejects_steering_ack_and_empty():
    ack = runner.STEERING_ACK
    # _ack 分支：token 與 done 同一個事件
    turn = runner.build_research_turn("q", [{"token": ack, "done": True, "session_id": "t"}], 1)
    assert "steering" in turn["error"]
    # _steer 分支：先 token 再 done
    turn = runner.build_research_turn("q", [{"token": ack}, {"done": True, "session_id": "t"}], 1)
    assert "steering" in turn["error"]
    # _drop 分支：只有 done
    turn = runner.build_research_turn("q", [{"done": True, "session_id": "t"}], 1)
    assert "沒有回答內容" in turn["error"]


def test_build_research_turn_error_and_cancel():
    assert runner.build_research_turn("q", [{"error": "忙碌", "done": True}], 1)["error"] == "忙碌"
    assert runner.build_research_turn("q", [{"done": True, "cancelled": True}], 1)["error"] == "cancelled"
    assert runner.build_research_turn("q", [{"token": "x"}], 1)["error"]


# ── Demo 案例 ───────────────────────────────────────────────────────────────

SCENARIO = {"id": "research-09", "assistant": "research", "category": "general", "title": "t",
            "scenario": "s", "project_id": "p1", "messages": ["a", "b"]}
PROJECT = {"id": "p1", "title": "研究", "department": "某系", "year": "112", "type": "E", "studentName": "王小明"}


def _turn(text="回答"):
    return {"user": "a", "assistant": text, "thread_id": "t1", "session_id": None, "latency_ms": 10,
            "model": "m", "input_tokens": 1, "output_tokens": 2, "error": None}


def test_build_case_strips_internal_fields_and_student_name():
    case = record.build_case(SCENARIO, [_turn(), _turn()], project=PROJECT, commit="abc", generated_at="now")
    assert "studentName" not in case["input"]["project"]
    assert all("thread_id" not in t and "session_id" not in t for t in case["turns"])
    assert case["review"]["status"] == "pending"
    assert case["meta"]["total_latency_ms"] == 20 and case["meta"]["models"] == ["m"]


def test_should_skip_protects_existing_cases(tmp_path):
    path = tmp_path / "x.json"
    assert record.should_skip(path, force=False) is None
    path.write_text(json.dumps({"review": {"status": "approved"}}), encoding="utf-8")
    assert "approved" in record.should_skip(path, force=False)
    assert record.should_skip(path, force=True) is None


def _approved_case(**over):
    case = record.build_case(SCENARIO, [_turn()], project=PROJECT, commit="abc", generated_at="now")
    case["review"].update(status="approved", reviewer="R")
    case.update(over)
    return case


def test_validate_flags_pii_and_student_name():
    case = _approved_case()
    case["turns"][0]["assistant"] = "請聯絡 0912-345-678 或 a@b.com，作者王小明"
    errs = validate.check_case(case, student_names={"p1": "王小明"}, require_approved=True)
    joined = " ".join(errs)
    assert "手機號碼" in joined and "email" in joined and "學生姓名" in joined


def test_content_hash_detects_manual_edit_but_allows_review():
    case = _approved_case()
    assert case["meta"]["content_sha256"] == validate.content_digest(case)
    case["review"].update(conclusion="人工填寫的結論", notes="ok")
    assert validate.check_case(case, student_names={}, require_approved=True) == []
    case["turns"][0]["assistant"] = "被手動改過的回答"
    errs = validate.check_case(case, student_names={}, require_approved=True)
    assert any("content_sha256" in e for e in errs)
    del case["meta"]["content_sha256"]
    assert any("缺少 content_sha256" in e for e in validate.check_case(case, student_names={}, require_approved=False))


def test_pii_check_covers_whole_turn():
    turn = _turn()
    turn["course_cards"] = [{"name": "課", "teacher": "聯絡 teacher@example.com"}]
    case = record.build_case(SCENARIO, [turn], project=PROJECT, commit="abc", generated_at="now")
    errs = validate.check_case(case, student_names={}, require_approved=False)
    assert any("email" in e for e in errs)


@pytest.mark.parametrize("text", [
    "身分證：\nA123456789",   # 行首（前一個字元是換行）
    "身分證：\tA123456789",   # 前面是 tab
    "A123456789",            # 整段只有號碼
])
def test_pii_detects_id_at_line_start(text):
    turn = _turn(text)
    case = record.build_case(SCENARIO, [turn], project=PROJECT, commit="abc", generated_at="now")
    errs = validate.check_case(case, student_names={}, require_approved=False)
    assert any("身分證字號" in e for e in errs), errs


def test_steering_ack_matches_backend_source():
    """STEERING_ACK 是複製自後端的字串；後端改字時這個測試會提醒同步更新。"""
    source = (ROOT / "backend" / "app" / "routes" / "projects.py").read_text(encoding="utf-8")
    assert source.count(runner.STEERING_ACK) >= 2


def test_validate_require_approved():
    case = _approved_case()
    case["review"]["status"] = "pending"
    assert validate.check_case(case, student_names={}, require_approved=False) == []
    assert validate.check_case(case, student_names={}, require_approved=True)


def test_scenarios_cover_competition_requirements():
    scenarios = record.load_scenarios()
    fake_cases = [{"id": s["id"], "assistant": s["assistant"], "category": s["category"]} for s in scenarios]
    assert validate.check_coverage(fake_cases) == []
    for s in scenarios:
        if s["assistant"] == "research":
            assert s.get("project_id"), s["id"]


# ── 評估題組 ─────────────────────────────────────────────────────────────────

def test_test_set_is_deterministic_and_committed():
    built = build_ts.build()
    assert built == build_ts.build()
    committed = json.loads((ROOT / "data" / "evaluation" / "test_set.json").read_text(encoding="utf-8"))
    assert committed == built, "data/evaluation/test_set.json 與腳本產生結果不一致，請重新產生或檢查資料變動"


def test_test_set_is_independent_from_demo():
    items = build_ts.build()["items"]
    assert 20 <= len(items) <= 30
    assert len({i["id"] for i in items}) == len(items)
    demo = json.loads((ROOT / "data" / "demo" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    demo_questions = {m for s in demo for m in s["messages"]}
    demo_projects = {s.get("project_id") for s in demo if s.get("project_id")}
    assert not demo_questions & {i["question"] for i in items}
    assert not demo_projects & {i["project_id"] for i in items if i["project_id"]}
    for i in items:
        if i["reference"]:
            assert i["reference"]["answer_points"] and "None" not in " ".join(i["reference"]["answer_points"])


# ── 評分統計 ─────────────────────────────────────────────────────────────────

def test_weighted_kappa():
    assert analyze.quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert analyze.quadratic_weighted_kappa([5, 5, 5], [5, 5, 5]) == 1.0
    # 完全相反 → 負值
    assert analyze.quadratic_weighted_kappa([1, 5, 1, 5], [5, 1, 5, 1]) < 0


def test_pass_rule():
    assert analyze.is_pass({"correctness": 4, "traceability": 3, "completion": 3, "safety": 4})
    assert not analyze.is_pass({"correctness": 3.5, "traceability": 5, "completion": 5, "safety": 5})
    assert not analyze.is_pass({"correctness": 5, "traceability": 2.5, "completion": 5, "safety": 5})


def _write_sheet(path: Path, rows: list[dict], scores: dict[str, tuple]):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=sheet.COLUMNS)
        writer.writeheader()
        for row in rows:
            s = scores[row["id"]]
            writer.writerow({**row, "correctness": s[0], "traceability": s[1], "completion": s[2], "safety": s[3],
                             "error_types": s[4] if len(s) > 4 else "", "notes": ""})


def test_end_to_end_score_sheet_and_analysis(tmp_path):
    responses = [
        {"id": "eval-c-01", "assistant": "course", "category": "factual", "difficulty": "easy",
         "question": "Q1", "answer": "A1", "process": ["工具 x"], "course_cards": ["課（系）"], "sources": []},
        {"id": "eval-r-01", "assistant": "research", "category": "research_method", "difficulty": "medium",
         "question": "Q2", "answer": "A2", "process": [], "course_cards": [], "sources": ["p.1"], "error": None},
    ]
    rows = sheet.build_rows(responses, {"eval-c-01": {"reference": {"answer_points": ["x"], "source": "s"},
                                                      "expected_behavior": "e"}})
    assert rows[0]["reference"].startswith("- x") and rows[1]["citations"] == "p.1"
    _write_sheet(tmp_path / "score_A.csv", rows, {"eval-c-01": (5, 4, 5, 5), "eval-r-01": (2, 2, 3, 5, "捏造,引用缺失")})
    _write_sheet(tmp_path / "score_B.csv", rows, {"eval-c-01": (5, 5, 5, 5), "eval-r-01": (3, 2, 3, 5, "捏造")})

    raters = {f.stem.removeprefix("score_"): analyze.load_rater(f) for f in sorted(tmp_path.glob("score_*.csv"))}
    summary = analyze.analyze(raters)
    assert summary["overall"]["pass_rate"] == 0.5
    assert summary["by_assistant"]["course"]["pass_rate"] == 1.0
    assert summary["error_types"] == {"捏造": 1, "引用缺失": 1}
    assert summary["inter_rater"]["dimensions"]["completion"]["exact"] == 1.0
    report = analyze.render_report(summary, {"run_id": "r", "git_commit": "c"})
    assert "通過率" in report and "eval-r-01" in report


def test_invalid_score_is_rejected(tmp_path):
    rows = sheet.build_rows([{"id": "x", "assistant": "course", "category": "c", "difficulty": "easy",
                              "question": "q", "answer": "a"}], {})
    _write_sheet(tmp_path / "score_A.csv", rows, {"x": (6, 1, 1, 1)})
    with pytest.raises(analyze.ScoreError, match="超出"):
        analyze.load_rater(tmp_path / "score_A.csv")
