from app.utils import new_id
from collections.abc import AsyncIterator
import asyncio
import time as _time
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.prompting.loader import load_stack
from app.services.ai_provider import get_chat_llm
from app.prompting.registry import get as get_prompt
from app.prompting.registry import version as prompt_version

from .types import AgentLimitation, AgentRoute, AgentResult, AgentStatus
from .request_context import get_user_id
from .runner import _AnswerExtractor, _turn_cost_var, _TurnCostAccumulator
from . import steering as _steering

logger = logging.getLogger(__name__)


# Background tasks fired by this module (memory writes, DB writes, evaluations).
# Tracked so they can be awaited during graceful shutdown.
_router_background_tasks: set[asyncio.Task] = set()


def _fire_and_forget(coro) -> None:
    task = asyncio.create_task(coro)
    _router_background_tasks.add(task)

    def _on_done(t: asyncio.Task) -> None:
        _router_background_tasks.discard(t)
        if not t.cancelled() and t.exception():
            logger.warning("Background task failed: %s", t.exception())

    task.add_done_callback(_on_done)


ROUTER_PROMPT_NAME = "route_coordinator"
VALID_AGENTS = {"chat", "retrieval", "research"}
MAX_HANDOFFS = 3
COMPOSE_MIN_CHARS = 600  # minimum research response length to trigger composition

_FOLLOWUP_SIGNALS = (
    "繼續", "再說", "補充", "更多", "詳細", "展開", "那", "那麼", "這個",
    "剛才", "你說的", "上面", "除此之外", "另外", "而且", "還有",
    "more", "continue", "elaborate", "expand", "follow up",
)


def _looks_like_followup(message: str) -> bool:
    text = (message or "").strip()
    if len(text) > 60:
        return False
    lower = text.lower()
    return any(sig in lower for sig in _FOLLOWUP_SIGNALS)


class RouterDecision(BaseModel):
    agent_name: str = Field(
        description="Exact agent to invoke: chat | retrieval | research"
    )
    reason: str = Field(default="")


@dataclass(frozen=True)
class ExecutionStep:
    agent_name: str
    observation_id: str
    trace_id: str
    kind: str = "primary"
    reason: str = ""


@dataclass(frozen=True)
class ExecutionPlan:
    trace_id: str
    route: AgentRoute
    steps: tuple[ExecutionStep, ...]

    @property
    def primary_step(self) -> ExecutionStep:
        return self.steps[0]

    @property
    def composition_step(self) -> ExecutionStep | None:
        return next((step for step in self.steps if step.kind == "composition"), None)

    @property
    def target_step(self) -> ExecutionStep:
        return next((step for step in self.steps if step.kind == "primary"), self.steps[0])


def _prompt_key(thread_id: str | None, document_id: int) -> str:
    return f"{thread_id or ''}:{document_id}"


async def _escalation_route_for(
    result: AgentResult,
    route: AgentRoute,
    user_message: str,
    document_id: int,
    thread_id: str | None,
    hop_count: int,
    visited_agents: frozenset[str],
) -> AgentRoute | None:
    if result.status.completed or hop_count + 1 >= MAX_HANDOFFS:
        return None
    guidance = _steering.get_and_clear(thread_id) if thread_id else None
    decision = await _orchestrate(
        user_message,
        document_id=document_id,
        previous_agent=route.agent_name,
        agent_status=result.status,
        steering_guidance=guidance,
    )
    if decision.agent_name == route.agent_name or decision.agent_name in visited_agents:
        return None
    return _route_for_agent(decision.agent_name, document_id, thread_id)


def _normalise_decision(decision: RouterDecision) -> RouterDecision:
    agent_name = decision.agent_name if decision.agent_name in VALID_AGENTS else "chat"
    return RouterDecision(agent_name=agent_name, reason=decision.reason)


def _primary_prompt(stack_name: str, base_name: str, thread_id: str | None, document_id: int):
    stack = load_stack(stack_name, _prompt_key(thread_id, document_id))
    return next((p for p in stack.prompts if p.base_name == base_name), stack.prompts[-1])


def _route_for_agent(
    agent_name: str,
    document_id: int,
    thread_id: str | None = None,
) -> AgentRoute:
    if agent_name not in VALID_AGENTS:
        agent_name = "chat"
    if agent_name == "research":
        prompt = _primary_prompt("research_runtime", "research_writer", thread_id, document_id)
        return AgentRoute(agent_name, prompt.name, prompt.version, compose_after=False)
    if agent_name == "retrieval":
        return AgentRoute(agent_name, "retrieval_capability", prompt_version("retrieval_capability"))
    return AgentRoute("chat", "chat_mode", prompt_version("chat_mode"))


def _fetch_document_context(document_id: int) -> dict | None:
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfDocument
    with PdfSessionLocal() as db:
        doc = (
            db.query(PdfDocument.id, PdfDocument.filename, PdfDocument.abstract_text)
            .filter(PdfDocument.id == document_id)
            .first()
        )
    if doc is None:
        return None
    return {
        "id": doc.id,
        "filename": doc.filename,
        "abstract": (doc.abstract_text or "")[:300],
    }


def _build_execution_plan(
    route: AgentRoute,
    *,
    trace_id: str,
    observation_id: str | None = None,
) -> ExecutionPlan:
    agent_name = route.agent_name
    steps: list[ExecutionStep] = [
        ExecutionStep(
            agent_name=agent_name,
            observation_id=observation_id or new_id(),
            trace_id=trace_id,
            kind="primary",
            reason=f"agent={agent_name}",
        )
    ]
    if route.compose_after and agent_name != "chat":
        steps.append(ExecutionStep(
            agent_name="chat",
            observation_id=new_id(),
            trace_id=trace_id,
            kind="composition",
            reason="final_composition",
        ))
    return ExecutionPlan(
        trace_id=trace_id,
        route=route,
        steps=tuple(steps),
    )


_router_llm = None


def _get_router_llm():
    global _router_llm
    if _router_llm is None:
        _router_llm = get_chat_llm(use_mini=True, temperature=0)
    return _router_llm


async def _orchestrate(
    message: str,
    document_id: int,
    previous_agent: str | None = None,
    is_followup: bool = False,
    agent_status: AgentStatus | None = None,
    steering_guidance: str | None = None,
) -> RouterDecision:
    system = get_prompt(ROUTER_PROMPT_NAME)

    _doc = await asyncio.to_thread(_fetch_document_context, document_id)

    user = {
        "message": message,
        "document_context": _doc["abstract"] if _doc else None,
        "previous_agent": previous_agent,
        "is_followup_signal": is_followup,
        "agent_status": {
            "completed": agent_status.completed,
            "work_summary": agent_status.work_summary,
            "gaps": agent_status.gaps,
            "agent_limitation": agent_status.agent_limitation,
        } if agent_status else None,
        "steering_guidance": steering_guidance,
        "available_agents": ["chat", "retrieval", "research"],
        "response_format": {
            "agent_name": "chat|retrieval|research",
            "reason": "short reason",
        },
    }
    try:
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system),
            ("human", "{payload}"),
        ])
        structured = _get_router_llm().with_structured_output(RouterDecision, include_raw=True)
        chain = prompt | structured
        raw_result: dict = await chain.ainvoke(
            {"payload": json.dumps(user, ensure_ascii=False)}
        )
        decision: RouterDecision = raw_result["parsed"]

        acc = _turn_cost_var.get()
        if acc is not None:
            raw_msg = raw_result.get("raw")
            if raw_msg is not None:
                u = getattr(raw_msg, "usage_metadata", None) or {}
                ri = u.get("input_tokens", 0)
                ro = u.get("output_tokens", 0)
                acc.router_input_tokens += ri
                acc.router_output_tokens += ro
                acc.input_tokens += ri
                acc.output_tokens += ro

        return _normalise_decision(decision)
    except Exception as exc:
        logger.warning("Orchestrator LLM failed; using conservative fallback: %s", exc)
        return RouterDecision(agent_name="retrieval", reason="fallback")


async def route_request(
    message: str,
    document_id: int,
    thread_id: str | None = None,
    previous_agent_name: str | None = None,
) -> AgentRoute:
    is_followup = _looks_like_followup(message)
    decision = await _orchestrate(
        message,
        document_id,
        previous_agent=previous_agent_name,
        is_followup=is_followup,
    )
    return _route_for_agent(decision.agent_name, document_id, thread_id)


async def _update_memory(
    agent_name: str,
    thread_id: str,
    user_id: str | None,
    document_id: int,
    question: str,
    result,
) -> None:
    from app.services.pdf_agent_memory import record_agent_memory
    await record_agent_memory(
        agent_name=agent_name,
        thread_id=thread_id,
        user_id=user_id,
        question=question,
        result=result,
        document_id=document_id,
    )


async def _update_chat_summary(thread_id: str, question: str, answer: str) -> None:
    from app.services.pdf_memory_service import update_chat_context_summary
    await update_chat_context_summary(thread_id, question, answer)


async def run_research_agent(
    user_message: str,
    thread_id: str,
    document_id: int,
    *,
    observation_id: str | None,
    trace_id: str | None = None,
    on_stage=None,
    on_token=None,
    bypass_cache: bool = False,
) -> AgentResult:
    from .research import run_research_task

    stack = load_stack("research_runtime", _prompt_key(thread_id, document_id))
    metadata = {
        "agent_name": "research",
        **stack.metadata(),
    }
    return await run_research_task(
        question=user_message,
        thread_id=thread_id,
        document_id=document_id,
        research_mode="research",
        metadata=metadata,
        observation_id=observation_id,
        on_stage=on_stage,
        on_token=on_token,
        max_searches=14,
        max_searches_per_slot=3,
        max_consecutive_no_new=2,
        trace_id=trace_id,
        bypass_cache=bypass_cache,
    )


async def _write_agent_message(
    *,
    thread_id: str,
    user_message: str,
    output_response: str,
    sources: list[str],
    route: AgentRoute,
    primary_observation_id: str,
    result: AgentResult | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    router_input_tokens: int = 0,
    router_output_tokens: int = 0,
    latency_ms: int = 0,
    model_name: str = "",
) -> None:
    user_id = get_user_id()  # capture ContextVar before entering thread
    def _write():
        from app.database_pdf import PdfSessionLocal
        from app.models.pdf_models import PdfAgentMessage, PdfConversation
        with PdfSessionLocal() as db:
            msg = PdfAgentMessage(
                message_id=new_id(),
                thread_id=thread_id,
                user_id=user_id,
                agent_name=route.agent_name,
                user_question=user_message,
                agent_answer=output_response,
                sources=sources,
                trace_summary=result.coverage_result if result else None,
                observation_id=primary_observation_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                router_input_tokens=router_input_tokens,
                router_output_tokens=router_output_tokens,
                latency_ms=latency_ms,
                model_name=model_name or None,
            )
            db.add(msg)
            conv = db.query(PdfConversation).filter_by(thread_id=thread_id).first()
            if conv:
                conv.last_agent_name = route.agent_name
                new_count = (conv.message_count or 0) + 1
                conv.message_count = new_count
                if new_count == 1 and not conv.title:
                    conv.title = user_message[:60]
            else:
                logger.warning("_write_agent_message: no conversation for thread=%s", thread_id)
            db.commit()
    try:
        await asyncio.to_thread(_write)
    except Exception as exc:
        logger.warning("_write_agent_message failed thread=%s: %s", thread_id, exc)


async def _finalize_plan(
    plan: ExecutionPlan,
    route: AgentRoute,
    thread_id: str,
    document_id: int,
    user_message: str,
    *,
    output_response: str | None,
    primary_observation_id: str,
    sources: list[str] | None = None,
    result: AgentResult | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    router_input_tokens: int = 0,
    router_output_tokens: int = 0,
    latency_ms: int = 0,
    model_name: str = "",
) -> None:
    if thread_id and output_response:
        _fire_and_forget(_write_agent_message(
            thread_id=thread_id,
            user_message=user_message,
            output_response=output_response,
            sources=sources or [],
            route=route,
            primary_observation_id=primary_observation_id,
            result=result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            router_input_tokens=router_input_tokens,
            router_output_tokens=router_output_tokens,
            latency_ms=latency_ms,
            model_name=model_name,
        ))
    if route.agent_name == "research" and result is not None:
        _fire_and_forget(_update_memory(
            "research", thread_id, get_user_id(), document_id, user_message, result
        ))


async def _run_composition(
    plan: ExecutionPlan,
    result: AgentResult,
    user_message: str,
    thread_id: str,
    document_id: int,
    use_mini: bool,
) -> AgentResult:
    composition_step = plan.composition_step
    if composition_step is None:
        return result
    from . import chat_agent
    return await chat_agent.compose_final_response(
        user_message=user_message,
        task_result=result,
        thread_id=thread_id,
        document_id=document_id,
        observation_id=composition_step.observation_id,
        trace_id=composition_step.trace_id,
        use_mini=use_mini,
    )


_AGENT_STAGE_LABELS: dict[str, str] = {
    "chat":      "直接回答中",
    "retrieval": "搜尋文件中",
}


async def route_agent_stream(
    user_message: str,
    thread_id: str,
    document_id: int | None = None,
    *,
    route: AgentRoute | None = None,
    trace_id: str | None = None,
    observation_id: str | None = None,
    on_stage=None,
    on_route=None,
    previous_agent_name: str | None = None,
    bypass_cache: bool = False,
    use_mini: bool = False,
) -> AsyncIterator[tuple[str, bool, list[str]]]:
    """Stream tokens. Multi-hop routing handled via while-loop (not recursion)."""
    from . import chat_agent, retrieval_agent

    if document_id is None:
        raise ValueError("document_id is required for PDF chat")

    trace_id = trace_id or new_id()
    _acc = _TurnCostAccumulator()
    _turn_cost_var.set(_acc)
    _wall_start = _time.monotonic()
    _visited: frozenset[str] = frozenset()
    _full_response: str | None = None
    last_sources: list[str] = []
    plan: "ExecutionPlan | None" = None
    step = None
    current_route: AgentRoute | None = None
    _hop = 0
    next_route: AgentRoute | None = route

    while _hop < MAX_HANDOFFS:

        from . import chat_jobs as _chat_jobs
        if _chat_jobs.is_cancelled(thread_id):
            logger.info("route_agent_stream cancelled thread_id=%s", thread_id)
            yield "", True, last_sources
            return

        if next_route is not None:
            current_route = next_route
            next_route = None
        else:
            current_route = await route_request(
                user_message, document_id, thread_id,
                previous_agent_name=previous_agent_name if _hop == 0 else None,
            )

        if on_route and _hop == 0:
            on_route(current_route)
        if on_stage and current_route.agent_name in _AGENT_STAGE_LABELS:
            on_stage(_AGENT_STAGE_LABELS[current_route.agent_name])

        plan = _build_execution_plan(
            current_route,
            trace_id=trace_id,
            observation_id=observation_id if _hop == 0 else None,
        )
        step = plan.target_step

        _streamed_response: list[str] = []
        agent_result: AgentResult | None = None

        try:
            if current_route.agent_name == "research":
                _rqueue: asyncio.Queue = asyncio.Queue()

                def _push_research_token(t: str) -> None:
                    _rqueue.put_nowait(("token", t))

                def _push_research_stage(msg: str) -> None:
                    if on_stage:
                        on_stage(msg)

                rtask = asyncio.create_task(
                    run_research_agent(
                        user_message, thread_id, document_id,
                        observation_id=step.observation_id,
                        trace_id=step.trace_id,
                        on_stage=_push_research_stage,
                        on_token=_push_research_token,
                        bypass_cache=bypass_cache,
                    )
                )
                rtask.add_done_callback(lambda _: _rqueue.put_nowait(None))

                _ans_extractor = _AnswerExtractor()
                streamed_tokens = False
                try:
                    while True:
                        event = await _rqueue.get()
                        if event is None:
                            if not _chat_jobs.is_cancelled(thread_id):
                                while not _rqueue.empty():
                                    rem = _rqueue.get_nowait()
                                    if rem is None:
                                        continue
                                    etype, val = rem
                                    if etype == "token":
                                        ans_part = _ans_extractor.process(val)
                                        if ans_part:
                                            _streamed_response.append(ans_part)
                                            yield ans_part, False, []
                                            streamed_tokens = True
                            break
                        etype, val = event
                        if etype == "token":
                            ans_part = _ans_extractor.process(val)
                            if ans_part:
                                _streamed_response.append(ans_part)
                                yield ans_part, False, []
                                streamed_tokens = True
                        if _chat_jobs.is_cancelled(thread_id):
                            rtask.cancel()
                            try:
                                await rtask
                            except (asyncio.CancelledError, Exception):
                                pass
                            break
                finally:
                    if not rtask.done():
                        rtask.cancel()
                        try:
                            await rtask
                        except (asyncio.CancelledError, Exception):
                            pass

                if rtask.cancelled():
                    raise asyncio.CancelledError("research task was cancelled")
                if rtask.exception():
                    raise rtask.exception()
                research_result = rtask.result()
                if not streamed_tokens:
                    _streamed_response.append(research_result.response)
                    chunk_size = 8
                    for _i in range(0, len(research_result.response), chunk_size):
                        yield research_result.response[_i:_i + chunk_size], False, []
                        await asyncio.sleep(0)
                last_sources = research_result.sources
                agent_result = research_result

            elif current_route.agent_name == "retrieval":
                _retrieval_response = ""
                _retrieval_sources: list[str] = []
                async for _item in retrieval_agent.stream(
                    user_message, thread_id, document_id,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                    on_stage=on_stage,
                    use_mini=use_mini,
                ):
                    _tok, _done, _src = _item
                    if _done:
                        _retrieval_sources = _src
                    else:
                        _retrieval_response += _tok
                        _streamed_response.append(_tok)
                        if plan.composition_step is None:
                            yield _item
                    if _chat_jobs.is_cancelled(thread_id):
                        break

                last_sources = _retrieval_sources
                _retrieval_has_answer = bool(_retrieval_sources) and len(_retrieval_response.strip()) >= 30
                agent_result = AgentResult(
                    response=_retrieval_response,
                    sources=_retrieval_sources,
                    agent_name="retrieval",
                    status=AgentStatus(
                        completed=_retrieval_has_answer,
                        gaps=[] if _retrieval_has_answer else ["未找到與問題相關的文件片段"],
                        agent_limitation=AgentLimitation.NONE if _retrieval_has_answer else AgentLimitation.SINGLE_POINT_LOOKUP,
                    ),
                )

            else:  # chat
                async for item in chat_agent.stream(
                    user_message, thread_id, document_id,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                    on_stage=on_stage,
                    use_mini=use_mini,
                ):
                    token, is_done, sources = item
                    if is_done == "interrupt":
                        yield item
                        return
                    if is_done:
                        last_sources = sources
                    else:
                        _streamed_response.append(token)
                        yield item
                    if _chat_jobs.is_cancelled(thread_id):
                        break

                _chat_full = "".join(_streamed_response)
                _chat_lines = _chat_full.strip().split("\n")
                if _chat_lines[-1].strip() == "[INSUFFICIENT_CONTEXT]":
                    _chat_full = "\n".join(_chat_lines[:-1]).strip()
                    _streamed_response = [_chat_full]
                    # Clear any tokens already sent to the frontend before escalating.
                    yield "", "replace", []
                    agent_result = AgentResult(
                        response=_chat_full,
                        sources=last_sources,
                        agent_name="chat",
                        status=AgentStatus(
                            completed=False,
                            work_summary="chat 無法從現有 context 充分回答",
                            agent_limitation=AgentLimitation.CONTEXT_INSUFFICIENT,
                        ),
                    )
                else:
                    if not _chat_jobs.is_cancelled(thread_id):
                        _fire_and_forget(_update_chat_summary(thread_id, user_message, _chat_full))

        except Exception:
            raise

        _full_response = "".join(_streamed_response) or None

        if (plan.composition_step is not None
                and not _chat_jobs.is_cancelled(thread_id)
                and len(_full_response or "") >= COMPOSE_MIN_CHARS):
            if on_stage:
                on_stage("組織回答中")
            _composed = await _run_composition(
                plan,
                AgentResult(response=_full_response or "", sources=last_sources,
                            agent_name=current_route.agent_name),
                user_message, thread_id, document_id, use_mini,
            )
            yield _composed.response, "replace", _composed.sources
            last_sources = _composed.sources
            _full_response = _composed.response

        if (agent_result is not None
                and not agent_result.status.completed
                and _hop + 1 < MAX_HANDOFFS):
            _esc = await _escalation_route_for(
                agent_result, current_route, user_message, document_id, thread_id,
                _hop, _visited | {current_route.agent_name},
            )
            if _esc is not None:
                if _streamed_response:
                    yield "", "replace", []
                _visited = _visited | {current_route.agent_name}
                next_route = _esc
                _hop += 1
                continue

        break

    # Clean up any unconsumed steering message to prevent pollution of future requests.
    if thread_id:
        _steering.get_and_clear(thread_id)

    _latency_ms = int((_time.monotonic() - _wall_start) * 1000)
    _turn_cost_var.set(None)

    if (plan is not None and step is not None and current_route is not None
            and not _chat_jobs.is_cancelled(thread_id)):
        await _finalize_plan(
            plan, current_route, thread_id, document_id, user_message,
            output_response=_full_response,
            primary_observation_id=step.observation_id,
            sources=last_sources,
            result=agent_result,
            input_tokens=_acc.input_tokens,
            output_tokens=_acc.output_tokens,
            router_input_tokens=_acc.router_input_tokens,
            router_output_tokens=_acc.router_output_tokens,
            latency_ms=_latency_ms,
            model_name=_acc.agent_model,
        )

    yield "", True, last_sources
