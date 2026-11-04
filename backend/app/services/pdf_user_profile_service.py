"""User profile memory service for PDF chat.

Stores a semantic profile for each user in LangGraph Store under
namespace (user_id, "user_profile") / key "profile".

The profile is updated after research agent responses via a background
LLM call that merges new observations into the existing profile JSON.
It is injected as a system message for research and chat agents.

Profile schema:
{
  "preferred_language": "Traditional Chinese | English | ...",
  "academic_background": "...",
  "topics_of_interest": ["...", "..."],
  "answer_style_preference": "..."
}
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_NAMESPACE_KEY = "user_profile"
_PROFILE_KEY = "profile"

_EXTRACT_PROMPT = """\
你是使用者畫像提取器。根據下方的問答，更新使用者畫像 JSON。

規則：
- 只更新有充分證據的欄位，沒有資訊的欄位保持原值
- preferred_language：使用者問題的主要語言（Traditional Chinese / English / 其他）
- academic_background：從問題推斷學術或職業背景（簡短描述，最多 40 字）
- topics_of_interest：從本次問題新增關鍵主題（string list，最多 8 個，去重）
- answer_style_preference：使用者偏好的回答風格（詳細 / 簡潔 / 條列 / 不確定）

請直接回傳 JSON，不要任何說明文字。

現有畫像：
{current_profile}

本次問答：
問題：{question}
回答摘要：{answer_snippet}
"""


async def get_user_profile(user_id: str) -> dict | None:
    """Fetch the user's profile from LangGraph Store. Returns None if not found."""
    try:
        from app.agents.pdf.runner import get_store
        store = get_store()
        if store is None:
            return None
        namespace = (user_id, _NAMESPACE_KEY)
        item = await store.aget(namespace, _PROFILE_KEY)
        if item and item.value:
            return item.value
    except Exception as exc:
        logger.debug("get_user_profile(%s) failed: %s", user_id, exc)
    return None


async def update_user_profile(user_id: str, question: str, answer: str) -> None:
    """Merge new observations into the user profile via a mini-model LLM call."""
    try:
        from app.agents.pdf.runner import get_store
        store = get_store()
        if store is None:
            return

        current = await get_user_profile(user_id) or {}

        from app.services.bedrock_client import make_chat_llm

        llm = make_chat_llm("mini", temperature=0.0)

        prompt = _EXTRACT_PROMPT.format(
            current_profile=json.dumps(current, ensure_ascii=False),
            question=question[:200],
            answer_snippet=answer[:300],
        )
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        raw = str(getattr(response, "content", response)).strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        updated = json.loads(raw)
        if not isinstance(updated, dict):
            return

        # Merge: keep existing keys if not updated
        merged = {**current, **updated}
        # De-duplicate topics_of_interest
        topics = merged.get("topics_of_interest") or []
        if isinstance(topics, list):
            seen: set[str] = set()
            deduped = []
            for t in topics:
                if t not in seen:
                    seen.add(t)
                    deduped.append(t)
            merged["topics_of_interest"] = deduped[:8]

        namespace = (user_id, _NAMESPACE_KEY)
        await store.aput(namespace, _PROFILE_KEY, merged)
        logger.debug("update_user_profile(%s): profile updated", user_id)
    except Exception as exc:
        logger.warning("update_user_profile(%s) failed (non-fatal): %s", user_id, exc)


def format_profile_for_injection(profile: dict | None) -> str | None:
    """Format user profile dict as a concise string for system message injection."""
    if not profile:
        return None
    lines: list[str] = []
    if lang := profile.get("preferred_language"):
        lines.append(f"偏好語言：{lang}")
    if bg := profile.get("academic_background"):
        lines.append(f"學術背景：{bg}")
    topics = profile.get("topics_of_interest") or []
    if topics:
        lines.append(f"關注主題：{', '.join(str(t) for t in topics[:6])}")
    if style := profile.get("answer_style_preference"):
        if style != "不確定":
            lines.append(f"回答偏好：{style}")
    return "\n".join(lines) if lines else None
