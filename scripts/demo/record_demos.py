"""
record_demos.py — 錄製比賽展示版的示範對話。

直接在程式內呼叫真實的課程助理 / 研究計畫助理（不經過 HTTP，也不寫入對話紀錄），
把完整回應（回答、課程卡、工具呼叫軌跡、引用段落）存成前端讀的靜態 JSON：

    frontend/public/demo/course-assistant.json
    frontend/public/demo/research-assistant.json

每次執行都會呼叫付費模型。重新錄製過的案例 reviewed 會重設為 false，
人工檢查、匿名化後再手動改回 true；前端正式版只顯示 reviewed 為 true 的案例。

用法（在 project/ 目錄下，需 .env 內的 Azure OpenAI / DB / Qdrant 設定）：
    python scripts/demo/record_demos.py                  # 錄全部
    python scripts/demo/record_demos.py --only course    # 只錄課程助理
    python scripts/demo/record_demos.py --ids course-climate research-air-pollution
    python scripts/demo/record_demos.py --dry-run        # 只列出會錄哪些，不呼叫模型
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

QUESTIONS = Path(__file__).with_name("demo_questions.json")
OUT_DIR = ROOT / "frontend" / "public" / "demo"
COURSE_OUT = OUT_DIR / "course-assistant.json"
RESEARCH_OUT = OUT_DIR / "research-assistant.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return ""


def _load_existing(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "cases": []}


def _write(path: Path, data: dict, recorded: list[dict], order: list[str]) -> None:
    """把新錄的案例合併進既有檔案，依題目檔的順序排列；沒重錄的案例原封不動。"""
    by_id = {c["id"]: c for c in data.get("cases", [])}
    by_id.update({c["id"]: c for c in recorded})
    data["cases"] = [by_id[i] for i in order if i in by_id]
    data["version"] = 1
    data["updated_at"] = _now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── 課程助理 ────────────────────────────────────────────────────────────────

def record_course_case(spec: dict) -> dict:
    from app.services import llm_service as llm

    history: list[dict] = []
    turns: list[dict] = []
    model = ""
    for question in spec["turns"]:
        tokens: list[str] = []
        trace: dict = {"toolCalls": [], "verify": None}
        pool_size = 0
        done: dict = {}
        for raw in llm.stream_with_tools(question=question, history=list(history)):
            if not raw.startswith("data: "):
                continue
            try:
                ev = json.loads(raw[6:])
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if kind == "token":
                tokens.append(ev.get("text", ""))
            elif kind == "verify_start":
                pool_size = ev.get("pool_size", 0)
            elif kind == "verify_done":
                trace["verify"] = {
                    "poolSize": pool_size,
                    "selected": ev.get("selected", []),
                    "filteredOut": ev.get("filtered_out", []),
                    "method": ev.get("method"),
                }
            elif kind == "error":
                raise RuntimeError(f"{spec['id']}: {ev.get('message')}")
            elif kind == "done":
                done = ev

        answer = done.get("final_answer") or "".join(tokens)
        server_trace = done.get("debug_trace") or {}
        trace["toolCalls"] = server_trace.get("toolCalls", [])
        model = done.get("model", model)
        turns.append({
            "user": question,
            "assistant": answer,
            "course_cards": done.get("course_cards", []),
            "tools_used": done.get("tools_used", []),
            "debug_trace": trace,
        })
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]

    return _case_meta(spec, model) | {"turns": turns}


# ── 研究計畫助理 ────────────────────────────────────────────────────────────

async def record_research_case(spec: dict, projects: dict[str, dict]) -> dict:
    from app.agents.pdf.router_agent import route_agent_stream

    project = projects.get(spec["project_id"])
    if not project or not project.get("documentId"):
        raise RuntimeError(f"{spec['id']}: 找不到 {spec['project_id']} 或它沒有 documentId")

    thread_id = f"demo-{spec['id']}-{uuid.uuid4().hex[:8]}"
    previous_agent: str | None = None
    turns: list[dict] = []
    for question in spec["turns"]:
        stages: list[str] = []
        agents: list[str] = []
        answer = ""
        sources: list[str] = []

        def _on_stage(msg: str) -> None:
            stages.append(msg)

        def _on_route(route) -> None:
            agents.append(route.agent_name)

        async for token, is_done, srcs in route_agent_stream(
            question,
            thread_id=thread_id,
            document_id=int(project["documentId"]),
            previous_agent_name=previous_agent,
            on_stage=_on_stage,
            on_route=_on_route,
            bypass_cache=True,
        ):
            if is_done == "replace":
                answer = token
                sources = srcs or sources
            elif is_done:
                sources = srcs or sources
                break
            else:
                answer += token

        previous_agent = agents[-1] if agents else previous_agent
        turns.append({
            "user": question,
            "assistant": answer,
            "sources": sources,
            "agents": agents,
            "stages": stages,
        })

    return _case_meta(spec, "") | {
        "project_id": spec["project_id"],
        "project_title": project["title"],
        "project_department": project["department"],
        "project_year": project["year"],
        "turns": turns,
    }


async def _record_research(specs: list[dict]) -> list[dict]:
    from app.agents.pdf.runner import setup_checkpointer, shutdown_checkpointer

    projects = {p["id"]: p for p in json.loads(
        (ROOT / "data" / "processed" / "projects.json").read_text(encoding="utf-8")
    )}
    await setup_checkpointer()
    try:
        try:
            from app.rag import warmup
            await warmup()
        except Exception as exc:  # 與後端啟動時相同：預熱失敗不致命
            print(f"  (RAG warmup failed, continuing: {exc})")
        out = []
        for spec in specs:
            print(f"  ▶ {spec['id']}")
            out.append(await record_research_case(spec, projects))
        return out
    finally:
        await shutdown_checkpointer()


def _case_meta(spec: dict, model: str) -> dict:
    return {
        "id": spec["id"],
        "title": spec["title"],
        "category": spec["category"],
        "summary": spec.get("summary", ""),
        "field": spec.get("field", ""),
        "origin": spec.get("origin", ""),  # 對應評測集題號（eval-set-v1），沒有則留空
        "reviewed": False,
        "recorded_at": _now(),
        "commit": _commit(),
        "model": model,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=["course", "research"])
    parser.add_argument("--ids", nargs="*", default=None, help="只重錄這些案例 id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    spec = json.loads(QUESTIONS.read_text(encoding="utf-8"))

    def pick(kind: str) -> list[dict]:
        if args.only and args.only != kind:
            return []
        items = spec[kind]
        return [c for c in items if args.ids is None or c["id"] in args.ids]

    course_specs, research_specs = pick("course"), pick("research")
    print(f"課程助理 {len(course_specs)} 組、研究助理 {len(research_specs)} 組")
    if args.dry_run:
        for c in course_specs + research_specs:
            print(f"  - {c['id']}  [{c['category']}]  {len(c['turns'])} 輪")
        return

    if course_specs:
        recorded = []
        for c in course_specs:
            print(f"  ▶ {c['id']}")
            recorded.append(record_course_case(c))
        _write(COURSE_OUT, _load_existing(COURSE_OUT), recorded, [c["id"] for c in spec["course"]])
        print(f"已寫入 {COURSE_OUT.relative_to(ROOT)}")

    if research_specs:
        if sys.platform == "win32":
            # psycopg async 不支援 Windows 預設的 ProactorEventLoop
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        recorded = asyncio.run(_record_research(research_specs))
        _write(RESEARCH_OUT, _load_existing(RESEARCH_OUT), recorded, [c["id"] for c in spec["research"]])
        print(f"已寫入 {RESEARCH_OUT.relative_to(ROOT)}")

    print("記得人工檢查、匿名化後，把確認過的案例 reviewed 改成 true，")
    print("再執行 python scripts/demo/build_demo_analytics.py 更新示範學生的個人分析。")


if __name__ == "__main__":
    main()
