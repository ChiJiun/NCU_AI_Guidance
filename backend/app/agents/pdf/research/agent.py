"""Shared entry point for document research tasks."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from langchain_aws import ChatBedrockConverse
from app.services.bedrock_client import make_chat_llm
from app.tools.rag_tool import set_query_expander_llm

from .research_graph import _hard_max_searches, _merge_stream_patch, _seed_keywords, final_rs_from_result, research_graph, get_or_build_research_graph  # noqa: F401
from .runtime_prompts import RESEARCH_BASE_STACK, research_base_stack_metadata
from .runtime_metadata import (
    RESEARCH_AGENT_NAME,
    SUMMARY_AGENT_NAME,
    RESEARCH_STACK_NAME,
    compact_prompt_summary as _compact_prompt_summary,
    graph_runtime_metadata as _graph_runtime_metadata,
    parse_json_field as _parse_json_field,
    runtime_prompt_specs as _runtime_prompt_specs,
)
from .state import ResearchGraphState, ResearchState
from .task_planner import create_research_plan, fallback_research_plan
from ..types import AgentLimitation, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

# Background tasks that should be awaited on shutdown.
_background_tasks: set[asyncio.Task] = set()

# Active RunControl objects for in-flight research graph runs.
# Populated by _run_graph_streaming; drained by request_all_drain() on shutdown.
_active_run_controls: set = set()


def request_all_drain(reason: str = "shutdown") -> None:
    """Signal all active research graph runs to stop at the next superstep boundary."""
    for ctrl in list(_active_run_controls):
        try:
            ctrl.request_drain(reason)
        except Exception:
            pass

def _llm() -> ChatBedrockConverse:
    return make_chat_llm("chat", temperature=0)


def _utcnow() -> datetime:
    # SQLAlchemy expects naive datetimes; strip tzinfo to stay consistent with DB column type.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _slot_label(state: dict, slot: str) -> str:
    for item in state.get("coverage_items", []) or []:
        if not isinstance(item, dict) or item.get("id") != slot:
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        if label:
            return label[:16]
    labels = {
        "motivation": "研究動機",
        "method": "研究方法",
        "results": "研究成果",
        "limitations": "研究限制",
        "research_motivation": "研究動機",
        "research_methods": "研究方法",
        "research_findings": "研究成果",
        "research_limitations": "研究限制",
    }
    return labels.get(slot, slot.replace("_", " ") if slot else "檢索項目")


async def _run_graph_streaming(
    initial_state: ResearchGraphState,
    graph_config: dict,
    on_stage: Callable[[str], None] | None,
    on_token: Callable[[str], None] | None = None,
    graph=None,
) -> ResearchGraphState:
    from langgraph.errors import GraphDrained
    from langgraph.runtime import RunControl

    state: dict = dict(initial_state)
    _graph = graph if graph is not None else research_graph
    control = RunControl()
    _active_run_controls.add(control)
    try:
        async for chunk in _graph.astream(
            initial_state,
            config=graph_config,
            stream_mode=["updates", "messages"],
            version="v2",
            durability="async",
            control=control,
        ):
            if chunk["type"] == "updates":
                for node_name, patch in chunk["data"].items():
                    if not isinstance(patch, dict):
                        continue
                    state = _merge_stream_patch(state, patch)
            elif chunk["type"] == "messages" and on_token:
                msg, metadata = chunk["data"]
                if msg.content and metadata.get("langgraph_node") == "writer":
                    on_token(msg.content)
    except GraphDrained:
        logger.info("research graph drained at superstep boundary (observation_id=%s)", state.get("observation_id"))
    finally:
        _active_run_controls.discard(control)
    return state


def _document_context(document_id: int) -> str:
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfDocument
    with PdfSessionLocal() as db:
        row = db.query(PdfDocument.id, PdfDocument.filename, PdfDocument.abstract_text).filter(
            PdfDocument.id == document_id
        ).first()
        return f"[{row.filename}]\n{row.abstract_text or ''}".strip() if row else ""


async def _emit_stage(on_stage, msg: str) -> None:
    """Call on_stage, awaiting it if async."""
    if not on_stage:
        return
    try:
        result = on_stage(msg)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        pass


async def _plan_research(
    llm,
    question: str,
    research_mode: str,
    context: str,
    on_stage: Callable[[str], None] | None,
) -> tuple[str, list[dict], str, list[str], int]:
    """Run LLM planning; falls back to keyword plan on failure.

    Returns (task_goal, coverage_items, output_contract, coverage_ids, llm_call_count).
    """
    await _emit_stage(on_stage, "分析任務：建立檢索項目")
    try:
        plan = await create_research_plan(
            llm,
            question=question,
            task_context=research_mode,
            document_context=context,
        )
        plan_llm_calls = 1
    except Exception:
        await _emit_stage(on_stage, "任務規劃失敗：使用預設檢索項目")
        plan = fallback_research_plan(research_mode, question)
        plan_llm_calls = 0

    task_goal, coverage_items, output_contract = plan.as_state_parts()
    coverage_ids = [item["id"] for item in coverage_items]
    await _emit_stage(on_stage, f"任務規劃完成：{len(coverage_ids)} 個檢索項目")
    return task_goal, coverage_items, output_contract, coverage_ids, plan_llm_calls


def _build_initial_graph_state(
    *,
    question: str,
    document_id: int,
    context: str,
    observation_id: str,
    thread_id: str,
    metadata: dict,
    max_searches: int,
    max_searches_per_slot: int,
    max_consecutive_no_new: int,
    min_evidence_per_slot: int,
    task_goal: str,
    coverage_items: list[dict],
    output_contract: str,
    coverage_ids: list[str],
    plan_llm_calls: int,
    started_at: datetime,
) -> "ResearchGraphState":
    """Build the initial LangGraph state dict from resolved plan and runtime params."""
    graph_metadata = _graph_runtime_metadata(metadata)
    required_count = len([i for i in coverage_items if i.get("required", True)]) or 1
    derived_max = required_count * max_searches_per_slot + 1
    # max_searches is a hard ceiling; only fall back to derived when not set.
    effective_max_searches = max_searches if max_searches > 0 else derived_max
    return {
        "question": question,
        "document_id": document_id,
        "document_context": context[:2000],
        "observation_id": observation_id,
        "thread_id": thread_id,
        "metadata": graph_metadata,
        "max_searches": effective_max_searches,
        "max_searches_per_slot": max_searches_per_slot,
        "max_consecutive_no_new": max_consecutive_no_new,
        "min_evidence_per_slot": min_evidence_per_slot,
        "task_goal": task_goal,
        "coverage_items": coverage_items,
        "output_contract": output_contract,
        "search_count": 0,
        "consecutive_no_new": 0,
        "known_keywords": _seed_keywords(context),
        "used_queries": [],
        "slot_status": {slot: "NOT_FILLED" for slot in coverage_ids},
        "evidence": {slot: [] for slot in coverage_ids},
        "evidence_details": {slot: [] for slot in coverage_ids},
        "sources": [],
        "last_reflection": "",
        "next_search_angle": "",
        "suggested_query_terms": [],
        "avoid_query_terms": [],
        "seen_chunk_keys": [],
        "used_query_keys": [],
        "scheduled_slot": None,
        "void_slot_attempts": {},
        "steps_json": [],
        "chunks_by_query_json": [],
        "trace_summary": {},
        "messages": [
            {"type": "system", "content": "研究流程由 runtime 控制：planner -> search_report -> reflector -> writer。"},
            {"type": "human", "content": question},
        ],
        "llm_call_count": plan_llm_calls,
        "started_at": started_at.isoformat(),
        "final_answer": "",
        "final_sources": [],
    }


async def run_research_task(
    *,
    question: str,
    thread_id: str,
    document_id: int,
    observation_id: str,
    metadata: dict,
    research_mode: str = "document_extraction",
    on_stage: Callable[[str], None] | None = None,
    on_token: Callable[[str], None] | None = None,
    max_searches: int = 10,
    max_searches_per_slot: int = 7,
    max_consecutive_no_new: int = 4,
    min_evidence_per_slot: int | None = None,
    trace_id: str | None = None,
    bypass_cache: bool = False,
) -> AgentResult:
    # Document extraction requires at least 1 evidence note per slot before the
    # writer fires; ad-hoc research has no such constraint.
    if min_evidence_per_slot is None:
        min_evidence_per_slot = 1 if research_mode == "document_extraction" else 0
    started_at = _utcnow()

    metadata = dict(metadata)
    base_stack_meta = research_base_stack_metadata()
    base_prompts = _parse_json_field(base_stack_meta.get("prompt_stack_json")) or []
    runtime_prompts = _runtime_prompt_specs()
    metadata["research_effective_base_stack_name"] = RESEARCH_BASE_STACK
    metadata["research_effective_base_prompt_stack_json"] = base_stack_meta.get("prompt_stack_json")
    metadata["research_effective_system_prompt_json"] = json.dumps([*base_prompts, *runtime_prompts], ensure_ascii=False)
    metadata["research_runtime_prompt_json"] = json.dumps(runtime_prompts, ensure_ascii=False)
    metadata["research_runtime_prompt_summary"] = _compact_prompt_summary(runtime_prompts)

    llm = _llm()
    set_query_expander_llm(llm)
    context = await asyncio.to_thread(_document_context, document_id)

    task_goal, coverage_items, output_contract, coverage_ids, plan_llm_calls = await _plan_research(
        llm, question, research_mode, context, on_stage
    )
    initial_state = _build_initial_graph_state(
        question=question, document_id=document_id, context=context,
        observation_id=observation_id, thread_id=thread_id, metadata=metadata,
        max_searches=max_searches, max_searches_per_slot=max_searches_per_slot,
        max_consecutive_no_new=max_consecutive_no_new,
        min_evidence_per_slot=min_evidence_per_slot,
        task_goal=task_goal, coverage_items=coverage_items,
        output_contract=output_contract, coverage_ids=coverage_ids,
        plan_llm_calls=plan_llm_calls, started_at=started_at,
    )

    try:
        from app.agents.pdf.runner import get_checkpointer as _get_checkpointer, get_store as _get_store
        _cp = _get_checkpointer()
        _st = _get_store()
    except Exception:
        _cp = None
        _st = None
    _graph = get_or_build_research_graph(checkpointer=_cp, store=_st)

    graph_config: dict = {
        "configurable": {
            "llm": llm,
            "on_stage": on_stage,
            "thread_id": observation_id,
        }
    }
    if plan_llm_calls == 0:
        # Task planning fell back to defaults → mark the entire graph run as WARNING
        graph_config["metadata"] = {
            "status": "WARNING",
            "status_message": "planning_fallback: using default research plan",
        }

    try:
        result = await _run_graph_streaming(initial_state, graph_config, on_stage, on_token, graph=_graph)
        answer = result["final_answer"]
        sources = result["final_sources"]
        final_state = final_rs_from_result(result)

        # ── Build structured coverage_result for downstream memory ────────────
        coverage_result = {
            slot: {
                "status": final_state.slot_status.get(slot, "NOT_FILLED"),
                "label": final_state.coverage_label(slot),
                "notes": [n[:150] for n in final_state.evidence.get(slot, [])[:2]],
            }
            for slot in final_state.coverage_ids()
        }

        _unfilled_gaps = [
            info.get("label") or slot
            for slot, info in coverage_result.items()
            if info.get("status") in ("NOT_FILLED", "NOT_FOUND", "EXHAUSTED")
        ]
        _research_status = AgentStatus(
            completed=len(_unfilled_gaps) == 0,
            work_summary="完成多步驟研究分析。",
            gaps=_unfilled_gaps,
            agent_limitation=AgentLimitation.NONE if len(_unfilled_gaps) == 0 else AgentLimitation.RESEARCH_BUDGET_EXHAUSTED,
        )
        return AgentResult(
            response=answer, sources=sources,
            agent_name=str(metadata.get("agent_name") or "research"),
            prompt_name=str(metadata.get("prompt_name") or "research_writer"),
            prompt_version=str(metadata.get("prompt_version") or "unknown"),
            observation_id=observation_id,
            coverage_result=coverage_result,
            status=_research_status,
        )
    except Exception as exc:
        logger.exception("run_research_task failed (observation_id=%s)", observation_id)
        raise


async def run_research_summary(
    *,
    question: str,
    thread_id: str,
    document_id: int,
    observation_id: str,
    metadata: dict,
    on_stage: Callable[[str], None] | None = None,
    max_searches: int = 10,
    max_searches_per_slot: int = 7,
    max_consecutive_no_new: int = 4,
) -> AgentResult:
    return await run_research_task(
        question=question,
        thread_id=thread_id,
        document_id=document_id,
        observation_id=observation_id,
        metadata=metadata,
        research_mode="document_extraction",
        on_stage=on_stage,
        max_searches=max_searches,
        max_searches_per_slot=max_searches_per_slot,
        max_consecutive_no_new=max_consecutive_no_new,
    )
