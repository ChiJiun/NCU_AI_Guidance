"""
record_demo_cases.py — 依 data/demo/scenarios.json 對真實後端發問，錄成比賽展示用的 Demo 案例

輸出：frontend/src/demo/cases/<id>.json（前端會在 build 時打包，展示時完全不呼叫模型）。

用法（需完整後端環境變數，且會真的呼叫 Bedrock、產生費用）：
  python scripts/demo/record_demo_cases.py --list
  python scripts/demo/record_demo_cases.py                 # 錄製所有尚未錄製的案例
  python scripts/demo/record_demo_cases.py --only course-01 research-02
  python scripts/demo/record_demo_cases.py --only course-01 --force   # 覆蓋已存在的案例

錄完之後：
  1. 人工逐一檢查回答（正確性、引用依據、匿名化），只在檔案的 review 區塊填寫
     status="approved"、reviewer、reviewed_at、conclusion（一兩句結論，前端會顯示）。
     不可修改 input／turns：meta.content_sha256 會在驗證時重算，內容有問題請修系統或情境後重錄。
  2. python scripts/demo/validate_demo_cases.py --require-approved
已經人工檢查過（status=approved）的案例，沒有 --force 不會被覆蓋，避免檢查結果被洗掉。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from assistant_runner import ROOT, AssistantRunner, git_commit, utc_now  # noqa: E402
from validate_demo_cases import content_digest  # noqa: E402

SCENARIOS = ROOT / "data" / "demo" / "scenarios.json"
CASES_DIR = ROOT / "frontend" / "src" / "demo" / "cases"

# 不輸出到前端的內部欄位（session／thread id 對訪客沒有意義）
_INTERNAL_TURN_FIELDS = {"session_id", "thread_id"}


def load_scenarios(path: Path = SCENARIOS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["scenarios"]


def load_projects() -> dict[str, dict]:
    projects = json.loads((ROOT / "data" / "processed" / "projects.json").read_text(encoding="utf-8"))
    return {p["id"]: p for p in projects}


def project_public_info(project: dict | None) -> dict | None:
    """前端只需要的研究計畫欄位；刻意不帶 studentName（匿名化）。"""
    if not project:
        return None
    return {k: project.get(k) for k in ("id", "title", "department", "year", "type")}


def build_case(scenario: dict, turns: list[dict], *, project: dict | None, commit: str, generated_at: str) -> dict:
    clean_turns = [{k: v for k, v in t.items() if k not in _INTERNAL_TURN_FIELDS} for t in turns]
    models = sorted({t.get("model") for t in turns if t.get("model")})
    case = {
        "id": scenario["id"],
        "assistant": scenario["assistant"],
        "category": scenario["category"],
        "title": scenario["title"],
        "scenario": scenario["scenario"],
        "input": {
            "messages": scenario["messages"],
            "project": project_public_info(project),
            "college": scenario.get("college"),
            "dept": scenario.get("dept"),
        },
        "turns": clean_turns,
        "meta": {
            "generated_at": generated_at,
            "git_commit": commit,
            "models": models,
            "total_latency_ms": sum(t.get("latency_ms", 0) for t in turns),
            "input_tokens": sum(t.get("input_tokens", 0) for t in turns),
            "output_tokens": sum(t.get("output_tokens", 0) for t in turns),
            "recorder": "scripts/demo/record_demo_cases.py",
        },
        "review": {"status": "pending", "reviewer": None, "reviewed_at": None, "notes": "", "conclusion": ""},
    }
    # 防止人工檢查時改到 AI 回答：validate_demo_cases.py 會重算比對
    case["meta"]["content_sha256"] = content_digest(case)
    return case


def should_skip(path: Path, force: bool) -> str | None:
    """回傳略過原因；None 表示要錄製。"""
    if not path.exists() or force:
        return None
    try:
        status = json.loads(path.read_text(encoding="utf-8")).get("review", {}).get("status")
    except (OSError, json.JSONDecodeError):
        return None
    return f"已存在（review.status={status}），要重錄請加 --force"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", help="只錄這些 id")
    parser.add_argument("--force", action="store_true", help="覆蓋已存在的案例（含已人工檢查者）")
    parser.add_argument("--list", action="store_true", help="只列出情境，不錄製")
    args = parser.parse_args()

    scenarios = load_scenarios()
    if args.only:
        wanted = set(args.only)
        unknown = wanted - {s["id"] for s in scenarios}
        if unknown:
            raise SystemExit(f"未知的情境 id：{sorted(unknown)}")
        scenarios = [s for s in scenarios if s["id"] in wanted]

    if args.list:
        for s in scenarios:
            path = CASES_DIR / f"{s['id']}.json"
            print(f"{s['id']:<12} {s['assistant']:<9} {s['category']:<18} {s['title']}  "
                  f"{'(已錄製)' if path.exists() else ''}")
        return

    todo = []
    for s in scenarios:
        reason = should_skip(CASES_DIR / f"{s['id']}.json", args.force)
        if reason:
            print(f"略過 {s['id']}：{reason}")
        else:
            todo.append(s)
    if not todo:
        print("沒有需要錄製的案例。")
        return

    projects = load_projects()
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    commit = git_commit()
    failed = []
    with AssistantRunner() as runner:
        for s in todo:
            project = projects.get(s.get("project_id")) if s.get("project_id") else None
            if s["assistant"] == "research" and project is None:
                print(f"✗ {s['id']}：找不到 project_id={s.get('project_id')}")
                failed.append(s["id"])
                continue
            print(f"→ 錄製 {s['id']}（{s['title']}）")
            turns = runner.run_conversation(s["assistant"], s["messages"], project_id=s.get("project_id"),
                                            college=s.get("college"), dept=s.get("dept"))
            errors = [t["error"] for t in turns if t.get("error")]
            if errors or len(turns) != len(s["messages"]):
                print(f"✗ {s['id']} 失敗，未寫入：{errors}")
                failed.append(s["id"])
                continue
            case = build_case(s, turns, project=project, commit=commit, generated_at=utc_now())
            out = CASES_DIR / f"{s['id']}.json"
            out.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"✓ {out.relative_to(ROOT)}（{case['meta']['total_latency_ms']} ms）")
    if failed:
        raise SystemExit(f"以下案例錄製失敗：{failed}")
    print("完成。請人工檢查後執行 validate_demo_cases.py --require-approved。")


if __name__ == "__main__":
    main()
