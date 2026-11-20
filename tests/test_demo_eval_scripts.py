"""評估用的後端執行器、示範對話驗證、30 題評估題組與評分統計腳本的測試（離線執行：不需網路、不呼叫模型）。"""
import csv
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


runner = _load("assistant_runner", "scripts/demo/assistant_runner.py")
validate = _load("validate_demos", "scripts/demo/validate_demos.py")
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


# ── 示範對話（frontend/public/demo/*.json）────────────────────────────────

PROJECTS = {"p1": {"id": "p1", "title": "研究", "studentName": "王小明"}}


def _case(text="回答", **over):
    case = {"id": "demo-1", "title": "t", "category": "一般", "summary": "s", "reviewed": True,
            "recorded_at": "2026-11-17T00:00:00+00:00", "project_id": "p1",
            "turns": [{"user": "問", "assistant": text, "sources": [], "agents": [], "stages": []}]}
    case.update(over)
    return case


def test_validate_flags_pii_and_student_name():
    errs = validate.check_case(_case("請聯絡 0912-345-678 或 a@b.com，作者王小明"), "research",
                               projects=PROJECTS, require_reviewed=True)
    joined = " ".join(errs)
    assert "手機號碼" in joined and "email" in joined and "學生姓名" in joined


def test_validate_flags_leftover_redaction_marker():
    errs = validate.check_case(_case("聯絡人是 <PRIVATE_PERSON>"), "research", projects=PROJECTS, require_reviewed=False)
    assert any("去識別化標記" in e for e in errs), errs


def test_pii_check_covers_whole_turn():
    case = _case()
    case["turns"][0]["course_cards"] = [{"name": "課", "teacher": "聯絡 teacher@example.com"}]
    errs = validate.check_case(case, "course", projects=PROJECTS, require_reviewed=False)
    assert any("course_cards[0].teacher" in e and "email" in e for e in errs), errs


@pytest.mark.parametrize("text", [
    "身分證：\nA123456789",   # 行首（前一個字元是換行）
    "身分證：\tA123456789",   # 前面是 tab
    "A123456789",            # 整段只有號碼
])
def test_pii_detects_id_at_line_start(text):
    errs = validate.check_case(_case(text), "course", projects=PROJECTS, require_reviewed=False)
    assert any("身分證字號" in e for e in errs), errs


def test_pii_no_cross_field_false_positive():
    case = _case("代碼 0912")
    case["turns"][0]["course_cards"] = [{"code": "0912345", "name": "678"}]
    assert validate.check_case(case, "course", projects=PROJECTS, require_reviewed=False) == []


def test_validate_require_reviewed_and_unknown_project():
    assert validate.check_case(_case(reviewed=False), "course", projects=PROJECTS, require_reviewed=False) == []
    assert validate.check_case(_case(reviewed=False), "course", projects=PROJECTS, require_reviewed=True)
    errs = validate.check_case(_case(project_id="nope"), "research", projects=PROJECTS, require_reviewed=False)
    assert any("找不到研究計畫" in e for e in errs)


def test_committed_demos_pass_validation():
    course, research, errors = validate.validate(ROOT / "frontend" / "public" / "demo", require_reviewed=True)
    assert errors == []
    assert len(course) >= validate.MIN_COURSE and len(research) >= validate.MIN_RESEARCH


def test_graduation_reference_always_contains_min_credits():
    import random

    def dept(rules):
        return {"id": "d", "name": "某系", "min_credits": 128, "required_courses": [{}], "graduation_rules": rules}

    # 有描述的 credit_minimum 在前 5 條 → 不重複補
    pts = build_ts.graduation_items([dept([{"type": "credit_minimum", "description": "最低 128 學分"}])],
                                    random.Random(0), 1)[0][0]["reference"]["answer_points"]
    assert pts == ["最低 128 學分"]
    # credit_minimum 沒有描述 → 要補上
    pts = build_ts.graduation_items([dept([{"type": "credit_minimum"}, {"type": "x", "description": "其他"}])],
                                    random.Random(0), 1)[0][0]["reference"]["answer_points"]
    assert pts[0] == "最低畢業學分：128"
    # credit_minimum 排在第 6 條之後 → 要補上
    rules = [{"type": "x", "description": f"規定{i}"} for i in range(5)] + [
        {"type": "credit_minimum", "description": "最低 128 學分"}]
    pts = build_ts.graduation_items([dept(rules)], random.Random(0), 1)[0][0]["reference"]["answer_points"]
    assert pts[0] == "最低畢業學分：128"


def test_steering_ack_matches_backend_source():
    """STEERING_ACK 是複製自後端的字串；後端改字時這個測試會提醒同步更新。"""
    source = (ROOT / "backend" / "app" / "routes" / "projects.py").read_text(encoding="utf-8")
    assert source.count(runner.STEERING_ACK) >= 2


def test_backend_interfaces_used_by_runner_exist():
    """assistant_runner 依賴的後端介面（靜態檢查，不 import 後端、不需後端套件）。

    後端改名或改路徑時這個測試會失敗，提醒同步更新 scripts/demo/assistant_runner.py。
    """
    import ast

    def top_level_names(rel: str) -> set[str]:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}

    assert {"AuthUser", "get_current_user", "get_optional_user"} <= top_level_names(
        "backend/app/services/auth_service.py")
    # runner 會覆寫 require_live_ai，讓錄製帳號在 LIVE_AI_ACCESS=developers 時也能通過 gate
    assert "require_live_ai" in top_level_names("backend/app/services/access_control.py")
    runner_src = (ROOT / "scripts" / "demo" / "assistant_runner.py").read_text(encoding="utf-8")
    assert "from app.services.access_control import require_live_ai" in runner_src
    assert "app.dependency_overrides[require_live_ai] = lambda: None" in runner_src
    main_src = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "app = FastAPI(" in main_src and '@app.get("/ready")' in main_src
    assert 'prefix="/api/chat"' in main_src and 'prefix="/api/projects"' in main_src
    chat_src = (ROOT / "backend" / "app" / "routes" / "chat.py").read_text(encoding="utf-8")
    assert '@router.post("/stream"' in chat_src  # 允許之後帶 dependencies 等參數
    for field in ("question", "session_id", "college", "dept"):
        assert f"    {field}:" in chat_src, field
    projects_src = (ROOT / "backend" / "app" / "routes" / "projects.py").read_text(encoding="utf-8")
    assert '@router.post("/{project_id}/chat/stream"' in projects_src


def _run_script(rel: str, *args: str):
    import subprocess

    return subprocess.run([sys.executable, str(ROOT / rel), *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def test_offline_cli_entrypoints():
    """不需後端、不呼叫模型的 CLI 路徑：參數解析、題組一致性檢查。"""
    check = _run_script("scripts/evaluation/build_test_set.py", "--check")
    assert check.returncode == 0, check.stdout + check.stderr
    for rel in ("scripts/demo/validate_demos.py", "scripts/evaluation/run_eval.py",
                "scripts/evaluation/make_score_sheet.py", "scripts/evaluation/analyze_scores.py"):
        helped = _run_script(rel, "--help")
        assert helped.returncode == 0, f"{rel}: {helped.stderr}"


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
    # 展示版的示範對話（scripts/demo/demo_questions.json）不可與評估題重複，研究計畫也不可重疊
    demo = json.loads((ROOT / "scripts" / "demo" / "demo_questions.json").read_text(encoding="utf-8"))
    demo_cases = demo["course"] + demo["research"]
    demo_questions = {t for c in demo_cases for t in c["turns"]}
    demo_projects = {c["project_id"] for c in demo["research"]}
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


# ── 資料庫保護 ──────────────────────────────────────────────────────────────

def test_runner_refuses_main_db_without_explicit_opt_in(monkeypatch):
    """沒設 RECORDER_DATABASE_URL 也沒明確允許時，必須在載入後端前就停止，不能寫進正式資料庫。"""
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("RECORDER_DATABASE_URL", raising=False)
    monkeypatch.delenv("RECORDER_ALLOW_MAIN_DB", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/main")
    with pytest.raises(SystemExit, match="RECORDER_DATABASE_URL"):
        runner.AssistantRunner().__enter__()
    assert os.environ["DATABASE_URL"] == "postgresql://example.invalid/main"
