"""
run_eval.py — 讓兩個 AI 助理回答 data/evaluation/test_set.json 的所有題目並記錄結果

輸出：data/evaluation/runs/<run_id>/
  - responses.jsonl  每題一行：題目、回答、分析過程、引用來源、耗時、錯誤
  - meta.json        執行時間、git commit、模型、題組版本

與 Demo 錄製共用 scripts/demo/assistant_runner.py：在同一個 process 內啟動真正的後端，
打真正的 SSE endpoint，所以評估的就是正式站台的行為。模型供應商沿用後端目前的設定；會真的呼叫模型、產生費用。

用法：
  python scripts/evaluation/run_eval.py                      # 全部 30 題
  python scripts/evaluation/run_eval.py --only eval-c-01 eval-r-03
  python scripts/evaluation/run_eval.py --run-id 2026-11-10-final

跑完後：python scripts/evaluation/make_score_sheet.py data/evaluation/runs/<run_id>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from assistant_runner import AssistantRunner, git_commit, utc_now  # noqa: E402

TEST_SET = ROOT / "data" / "evaluation" / "test_set.json"
RUNS_DIR = ROOT / "data" / "evaluation" / "runs"


def summarize_process(turn: dict) -> list[str]:
    """把分析過程整理成評分者看得懂的步驟文字。"""
    out: list[str] = []
    for step in turn.get("steps") or []:
        if step.get("kind") == "tool":
            out.append(f"工具 {step.get('tool')}（{step.get('count')} 筆）")
        elif step.get("kind") == "verify":
            out.append(f"驗證：{step.get('pool_size')} 門候選保留 {len(step.get('selected') or [])} 門")
    if turn.get("agent"):
        out.append(f"路由：{turn['agent'].get('label')}")
    out.extend(turn.get("stages") or [])
    return out


def to_record(item: dict, turn: dict) -> dict:
    return {
        "id": item["id"],
        "assistant": item["assistant"],
        "category": item["category"],
        "difficulty": item["difficulty"],
        "project_id": item.get("project_id"),
        "question": item["question"],
        "answer": turn.get("assistant", ""),
        "process": summarize_process(turn),
        "course_cards": [f"{c.get('name')}（{c.get('dept')}）" for c in turn.get("course_cards") or []],
        "sources": turn.get("sources") or [],
        "model": turn.get("model", ""),
        "latency_ms": turn.get("latency_ms", 0),
        "input_tokens": turn.get("input_tokens", 0),
        "output_tokens": turn.get("output_tokens", 0),
        "error": turn.get("error"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()

    test_set = json.loads(TEST_SET.read_text(encoding="utf-8"))
    items = test_set["items"]
    if args.only:
        items = [it for it in items if it["id"] in set(args.only)]
    out_dir = RUNS_DIR / args.run_id
    if out_dir.exists():
        raise SystemExit(f"{out_dir} 已存在，請換一個 --run-id，避免覆蓋已評分的結果")
    out_dir.mkdir(parents=True)

    started = utc_now()
    failures = 0
    with AssistantRunner() as runner, (out_dir / "responses.jsonl").open("w", encoding="utf-8") as fh:
        for item in items:
            print(f"→ {item['id']} {item['question'][:40]}")
            try:
                if item["assistant"] == "course":
                    turn = runner.ask_course(item["question"])
                else:
                    turn = runner.ask_research(item["project_id"], item["question"])
            except Exception as exc:  # noqa: BLE001 — 記錄失敗、繼續下一題
                turn = {"assistant": "", "error": f"{type(exc).__name__}: {exc}"}
            record = to_record(item, turn)
            failures += bool(record["error"])
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()

    meta = {
        "run_id": args.run_id,
        "started_at": started,
        "finished_at": utc_now(),
        "git_commit": git_commit(),
        "test_set_version": test_set.get("version"),
        "items": len(items),
        "system_errors": failures,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"完成：{len(items)} 題，系統錯誤 {failures} 題 → {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
