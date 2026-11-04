"""Core search logic: AgentContext, query expansion, HyDE, run_search_report.

Separated from rag_tool.py (LangChain @tool adapters) so the business logic
can be imported and tested independently of LangChain tool infrastructure.
"""
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.rag import (
    acount_document_chunks as _acount_document_chunks,
    aget_document_language as _aget_document_language,
    search_documents as _search_documents,
)

logger = logging.getLogger(__name__)

_MAX_SEARCHES = 8
_MAX_CONSECUTIVE_EMPTY = 3


def _emit_stage_sync(on_stage, msg: str) -> None:
    if not on_stage:
        return
    try:
        result = on_stage(msg)
        if asyncio.iscoroutine(result):
            try:
                asyncio.get_running_loop().create_task(result)
            except RuntimeError:
                result.close()
    except Exception:
        pass


@dataclass
class AgentContext:
    """Runtime state shared across tool calls during one request."""

    document_id: int | None = None
    agent_name: str | None = None
    seen_chunks: set = field(default_factory=set)
    search_count: int = 0
    consecutive_empty: int = 0
    on_stage: Callable[[str], None] | None = None
    max_searches: int | None = None
    max_consecutive_empty: int | None = None
    thread_id: str | None = None
    observation_id: str | None = None
    tool_sources: list[str] = field(default_factory=list)
    _memory_context: dict | None = field(default=None, repr=False)
    # Task prompt injected by _memory_prompt (not stored in LangGraph state)
    task_prompt: "str | list[str] | None" = field(default=None, repr=False)
    # Cached per-request values (document metadata never changes mid-conversation)
    _cached_total_chunks: int | None = field(default=None, repr=False)
    _cached_lang: str | None = field(default=None, repr=False)
    _cached_abstracts_text: str | None = field(default=None, repr=False)


class SearchInput(BaseModel):
    display_intent: str = Field(default="", description="Optional short UI label for this search.")
    keyword_query: str = Field(default="", description="Optional keyword-style query for sparse/BM25 retrieval.")
    semantic_query: str = Field(default="", description="Optional semantic sentence for dense retrieval.")
    section_terms: list[str] = Field(default_factory=list, description="Section or chapter names (e.g. '研究方法', 'conclusion'). When provided, section-level metadata filtering is attempted before semantic search.")
    query: str = Field(
        default="",
        description=(
            "Precise search query for ONE focused topic only. "
            "For follow-up searches, include 1-3 document-specific terms learned from prior evidence."
        ),
    )
    sub_queries: list[str] = Field(
        default_factory=list,
        description="Optional alternative phrasings of the SAME topic, max 2.",
    )
    use_hyde: bool = Field(default=False, description="Enable one HyDE expansion only when normal retrieval is weak or empty.")

    @field_validator("section_terms")
    @classmethod
    def _cap_section_terms(cls, v: list[str]) -> list[str]:
        return [s[:50] for s in v[:4]]


_HYDE_PROMPT = (
    "Write a short hypothetical passage (2-4 sentences) that could appear in the same "
    "research report and would help retrieve evidence for the query. Use only the topic, "
    "known evidence terms, gaps, and search intent supplied by the query. Do not invent "
    "facts as final evidence. Return only the passage."
)

_query_expander_llm = None


def set_query_expander_llm(llm) -> None:
    global _query_expander_llm
    _query_expander_llm = llm


def _get_query_expander_llm():
    global _query_expander_llm
    if _query_expander_llm is None:
        from app.services.bedrock_client import make_chat_llm
        _query_expander_llm = make_chat_llm("chat", temperature=0.3)
    return _query_expander_llm


def expand_queries(
    query: str,
    sub_queries: list[str] | None = None,
    target_lang: str = "auto",
    keyword_query: str = "",
    semantic_query: str = "",
    section_terms: list[str] | None = None,
) -> list[str]:
    raw_queries = [
        keyword_query,
        semantic_query,
        " ".join(section_terms or []),
        query,
        *(sub_queries or [])[:2],
    ]
    queries: list[str] = []
    for raw in raw_queries:
        cleaned = " ".join(str(raw or "").split())
        if cleaned and cleaned not in queries:
            queries.append(cleaned)
    return queries


async def _hyde_expand(
    queries: list[str],
    *,
    query: str = "",
    keyword_query: str = "",
    semantic_query: str = "",
    section_terms: list[str] | None = None,
) -> list[str]:
    if not queries:
        return queries
    try:
        hyde = await _get_query_expander_llm().ainvoke([
            SystemMessage(content=_HYDE_PROMPT),
            HumanMessage(content=(
                f"semantic_query: {semantic_query or query or keyword_query}\n"
                f"keyword_query: {keyword_query}\n"
                f"section_terms: {' '.join(section_terms or [])}"
            )),
        ])
        passage = hyde.content.strip()
        if passage and passage not in queries:
            return [*queries, passage]
    except Exception:
        pass
    return queries


async def run_search_report(
    query: str,
    ctx: AgentContext,
    sub_queries: list[str] | None = None,
    display_intent: str = "",
    keyword_query: str = "",
    semantic_query: str = "",
    section_terms: list[str] | None = None,
    use_hyde: bool = False,
) -> str:
    if ctx.document_id is None:
        raise ValueError("document_id is required for PDF document search")

    max_searches = ctx.max_searches or _MAX_SEARCHES
    max_empty = ctx.max_consecutive_empty or _MAX_CONSECUTIVE_EMPTY

    if ctx.search_count >= max_searches:
        return json.dumps(
            {"results": [], "HARD_STOP": f"Search limit reached ({max_searches}). Use collected evidence to answer."},
            ensure_ascii=False,
        )

    if ctx.consecutive_empty >= max_empty:
        return json.dumps(
            {"results": [], "HARD_STOP": f"{max_empty} consecutive searches found nothing new. Use collected evidence to answer."},
            ensure_ascii=False,
        )

    ctx.search_count += 1

    label = display_intent or keyword_query or query
    short_q = label[:30] + ("..." if len(label) > 30 else "")
    _emit_stage_sync(ctx.on_stage, f"搜尋文件：{short_q}")

    if ctx._cached_total_chunks is None:
        ctx._cached_total_chunks = await _acount_document_chunks(ctx.document_id)
    total_chunks = ctx._cached_total_chunks
    if total_chunks > 0 and len(ctx.seen_chunks) >= total_chunks:
        return json.dumps(
            {"results": [], "HARD_STOP": f"All {total_chunks} chunks already reviewed. Use collected evidence to answer."},
            ensure_ascii=False,
        )

    if ctx._cached_lang is None:
        ctx._cached_lang = await _aget_document_language(ctx.document_id)
    lang = ctx._cached_lang
    queries = expand_queries(
        query, sub_queries, target_lang=lang,
        keyword_query=keyword_query, semantic_query=semantic_query, section_terms=section_terms,
    )
    _hyde_already_tried = False
    if use_hyde:
        queries = await _hyde_expand(
            queries, query=query, keyword_query=keyword_query,
            semantic_query=semantic_query, section_terms=section_terms,
        )
        _hyde_already_tried = True
    if not queries:
        ctx.consecutive_empty += 1
        return json.dumps({"results": [], "message": "No retrieval query was provided."}, ensure_ascii=False)

    chunks, _ = await _search_documents(
        queries,
        document_id=ctx.document_id,
        top_n=4,
        lang=lang,
        exclude_chunk_keys=ctx.seen_chunks,
    )
    for _c in chunks:
        _p = _c.get("page", "?")
        _pe = _c.get("page_end", _p)
        _src = f"p.{_p}-{_pe}" if _pe != _p else f"p.{_p}"
        if _src not in ctx.tool_sources:
            ctx.tool_sources.append(_src)

    if not chunks and not _hyde_already_tried:
        hyde_queries = await _hyde_expand(
            queries, query=query, keyword_query=keyword_query,
            semantic_query=semantic_query, section_terms=section_terms,
        )
        if len(hyde_queries) > len(queries):
            chunks, _ = await _search_documents(
                hyde_queries,
                document_id=ctx.document_id,
                top_n=4,
                lang=lang,
                exclude_chunk_keys=ctx.seen_chunks,
            )
            for _c in chunks:
                _p = _c.get("page", "?")
                _pe = _c.get("page_end", _p)
                _src = f"p.{_p}-{_pe}" if _pe != _p else f"p.{_p}"
                if _src not in ctx.tool_sources:
                    ctx.tool_sources.append(_src)
            if chunks:
                logger.debug("run_search_report: HyDE fallback found %d chunks for %r", len(chunks), query[:60])

    for chunk in chunks:
        ctx.seen_chunks.add(hashlib.md5(chunk["content"].encode("utf-8", errors="replace")).hexdigest())

    if not chunks:
        ctx.consecutive_empty += 1
        return json.dumps(
            {"results": [], "message": "No results found. Try narrower keywords, synonyms, or related concepts."},
            ensure_ascii=False,
        )

    ctx.consecutive_empty = 0
    return json.dumps({"results": chunks}, ensure_ascii=False)
