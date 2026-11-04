from app.utils import new_id
from collections.abc import AsyncIterator
from datetime import datetime, timezone
import asyncio
import json
import logging
from typing import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_aws import ChatBedrockConverse

from app.services.bedrock_client import make_chat_llm
from .no_tool_runner import run_no_tool_agent, stream_no_tool_agent
from .request_context import get_user_id  # noqa: F401
from app.prompting.loader import load_stack

from .types import AgentLimitation, AgentResult, AgentStatus

STACK_NAME = "chat_default"
PROMPT_NAME = "chat_mode"
AGENT_NAME = "chat"

logger = logging.getLogger(__name__)


async def _emit_stage(on_stage, msg: str) -> None:
    if not on_stage:
        return
    try:
        result = on_stage(msg)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        pass


def _llm(use_mini: bool = False) -> ChatBedrockConverse:
    return make_chat_llm("mini" if use_mini else "chat", temperature=0.2)


async def compose_final_response(
    *,
    user_message: str,
    task_result: AgentResult,
    thread_id: str,
    document_id: int,
    observation_id: str | None = None,
    trace_id: str | None = None,
    use_mini: bool = False,
) -> AgentResult:
    """Format a task-agent result for the user without routing or tool access."""
    observation_id = observation_id or new_id()
    stack = load_stack(STACK_NAME)
    metadata = {
        "agent_name": AGENT_NAME,
        **stack.metadata(),
    }
    # Use only the core rules (first prompt in stack), not chat_mode.
    # chat_mode adds educational elaborations that inflate the composition output.
    core_content = stack.contents[0] if stack.contents else ""
    system_messages = [
        SystemMessage(content=core_content),
        SystemMessage(content=(
            "你是最終回覆格式化層。將 task_answer 直接呈現給使用者。"
            "不添加 task_answer 未提及的內容、事實或資訊。"
            "不補充背景知識、不延伸解說、不加評論。"
            "保留所有技術術語、分類名稱和專有名詞原文。"
            "不引用來源、文件名稱或頁碼。"
            "語言與使用者問題一致。"
        )),
    ]
    payload = {
        "user_message": user_message,
        "task_agent": task_result.agent_name,
        "task_answer": task_result.response,
        "response_contract": {
            "language": "Match the user's language.",
            "do_not_add_new_facts": True,
            "do_not_append_sources": True,
        },
    }
    messages = [
        *system_messages,
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]
    response = await _llm(use_mini=use_mini).with_config({
        "run_name": "chat_compose",
        "metadata": {
            "agent_name": AGENT_NAME,
            "thread_id": thread_id,
            "trace_id": trace_id or "",
            "observation_id": observation_id,
            **{k: v for k, v in metadata.items() if isinstance(v, str)},
        },
    }).ainvoke(messages)
    content = str(getattr(response, "content", response)).strip()
    return AgentResult(
        response=content,
        sources=task_result.sources,
        agent_name=AGENT_NAME,
        prompt_name=str(metadata.get("prompt_name", PROMPT_NAME)),
        prompt_version=str(metadata.get("prompt_version", "unknown")),
        observation_id=observation_id,
        status=AgentStatus(
            completed=True,
            work_summary="從對話 context 和文件摘要回答。",
        ),
    )


async def answer(
    user_message: str,
    thread_id: str,
    document_id: int,
    *,
    observation_id: str | None = None,
    trace_id: str | None = None,
    on_stage: Callable[[str], None] | None = None,
    use_mini: bool = False,
) -> AgentResult:
    stack = load_stack(STACK_NAME)
    meta = {
        "agent_name": AGENT_NAME,
        **stack.metadata(),
    }
    await _emit_stage(on_stage, "組織回答中")
    observation_id = observation_id or new_id()

    # Inject memory context (context_summary + long_term + user_profile)
    extra_msgs: list[str] = [
        "You do not have retrieval tools in this step. If the request "
        "requires document evidence, answer only from context already "
        "provided by the router or state that the router should use a "
        "retrieval/research route."
    ]
    try:
        from app.services.pdf_agent_memory import build_memory_context, format_memory_system_messages
        memory = await build_memory_context(
            AGENT_NAME, thread_id, get_user_id(), user_message, document_id
        )
        extra_msgs = format_memory_system_messages(memory) + extra_msgs
    except Exception as _exc:
        logger.debug("chat_agent.answer: memory context failed (non-fatal): %s", _exc)

    response, sources, meta, observation_id = await run_no_tool_agent(
        user_message=user_message,
        thread_id=thread_id,
        document_id=document_id,
        stack_name=STACK_NAME,
        agent_name=AGENT_NAME,
        observation_id=observation_id,
        trace_id=trace_id,
        use_mini=use_mini,
        extra_system_messages=extra_msgs,
    )
    _lines = response.strip().split("\n")
    _insufficient = _lines[-1].strip() == "[INSUFFICIENT_CONTEXT]"
    response = "\n".join(_lines[:-1]).strip() if _insufficient else response.strip()

    return AgentResult(
        response=response,
        sources=sources,
        agent_name=AGENT_NAME,
        prompt_name=str(meta.get("prompt_name", PROMPT_NAME)),
        prompt_version=str(meta.get("prompt_version", "unknown")),
        observation_id=observation_id,
        status=AgentStatus(
            completed=not _insufficient,
            work_summary="直接從對話 context 回答。",
            agent_limitation=AgentLimitation.CONTEXT_INSUFFICIENT if _insufficient else AgentLimitation.NONE,
        ),
    )


async def stream(
    user_message: str,
    thread_id: str,
    document_id: int,
    *,
    observation_id: str | None = None,
    trace_id: str | None = None,
    on_stage: Callable[[str], None] | None = None,
    use_mini: bool = False,
) -> AsyncIterator[tuple[str, bool, list[str]]]:
    observation_id = observation_id or new_id()
    await _emit_stage(on_stage, "組織回答中")

    extra_msgs: list[str] = [
        "You do not have retrieval tools in this step. If the request "
        "requires document evidence, answer only from context already "
        "provided by the router or state that the router should use a "
        "retrieval/research route."
    ]
    try:
        from app.services.pdf_agent_memory import build_memory_context, format_memory_system_messages
        memory = await build_memory_context(
            AGENT_NAME, thread_id, get_user_id(), user_message, document_id
        )
        extra_msgs = format_memory_system_messages(memory) + extra_msgs
    except Exception as _exc:
        logger.debug("chat_agent.stream: memory context failed (non-fatal): %s", _exc)

    async for token in stream_no_tool_agent(
        user_message=user_message,
        thread_id=thread_id,
        document_id=document_id,
        stack_name=STACK_NAME,
        agent_name=AGENT_NAME,
        observation_id=observation_id,
        trace_id=trace_id,
        use_mini=use_mini,
        extra_system_messages=extra_msgs,
    ):
        yield token, False, []
    yield "", True, []
