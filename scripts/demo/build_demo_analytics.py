"""
build_demo_analytics.py — 把錄好的示範對話當成「一位示範學生」的探索紀錄，
用和正式版完全相同的計算邏輯算出個人分析，存成：

    frontend/public/demo/analytics.json

展示版的訪客看不到自己的分析（不能提問、沒有紀錄），個人分析頁改顯示這份示範。
不呼叫任何模型；record_demos.py 錄完會自動執行，也可以單獨跑：

    python scripts/demo/build_demo_analytics.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

DEMO_DIR = ROOT / "frontend" / "public" / "demo"
PROCESSED = ROOT / "data" / "processed"


def _load(name: str) -> list[dict]:
    path = DEMO_DIR / name
    if not path.exists():
        return []
    cases = json.loads(path.read_text(encoding="utf-8")).get("cases", [])
    return [c for c in cases if c.get("reviewed")]


def _when(case: dict, offset: int) -> datetime:
    try:
        base = datetime.fromisoformat(case["recorded_at"])
    except (KeyError, ValueError):
        base = datetime.now(timezone.utc)
    return base + timedelta(seconds=offset)


def build() -> dict:
    from app.services.session_store import compute_course_analytics, compute_pdf_analytics

    college_map = json.loads((PROCESSED / "dept_college_map.json").read_text(encoding="utf-8"))

    # ── 課程助理：每組示範 = 一段對話，每輪 = 一筆 chat_turn ─────────────
    course_cases = _load("course-assistant.json")
    rows = [
        {
            "tools_used": t.get("tools_used", []),
            # 示範檔沒有存完整候選池，以推薦課程卡當作探索過的課程
            "course_pool": t.get("course_cards", []),
            "course_cards": t.get("course_cards", []),
        }
        for c in course_cases
        for t in c["turns"]
    ]
    course = compute_course_analytics(rows, len(course_cases), college_map)

    # ── 研究計畫助理：每組示範 = 一段對話，綁定一份研究計畫 ─────────────
    research_cases = _load("research-assistant.json")
    projects = {p["id"]: p for p in json.loads((PROCESSED / "projects.json").read_text(encoding="utf-8"))}
    doc_meta: dict[int, dict] = {}
    convs, counts, recent = [], {}, []
    for c in research_cases:
        project = projects.get(c["project_id"])
        if not project or project.get("documentId") is None:
            continue
        doc_id = int(project["documentId"])
        doc_meta[doc_id] = {k: project.get(k, "") for k in ("title", "department", "year")}
        thread = c["id"]
        convs.append({"thread_id": thread, "document_id": doc_id, "created_at": _when(c, 0)})
        counts[thread] = len(c["turns"])
        recent += [
            {"thread_id": thread, "user_question": t["user"], "created_at": _when(c, i)}
            for i, t in enumerate(c["turns"])
        ]
    convs.sort(key=lambda x: x["created_at"], reverse=True)
    recent.sort(key=lambda x: x["created_at"], reverse=True)
    project = compute_pdf_analytics(convs, counts, recent, doc_meta, college_map)

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"course_cases": len(course_cases), "research_cases": len(research_cases)},
        "course": course,
        "project": project,
    }


def main() -> None:
    data = build()
    out = DEMO_DIR / "analytics.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    src = data["source"]
    print(f"已寫入 {out.relative_to(ROOT)}（課程 {src['course_cases']} 組、研究 {src['research_cases']} 組）")


if __name__ == "__main__":
    main()
