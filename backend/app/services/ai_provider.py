"""AI 供應商開關：決定對話／推理 LLM 走 Azure OpenAI 還是 Amazon Bedrock（Claude）。

環境變數 ``AI_PROVIDER``：

- ``azure``（預設；未設定或空字串也是 azure）：行為與切換前完全相同。
- ``bedrock``：所有對話／推理 LLM 改用 Bedrock 上的 Claude（設定見 ``bedrock_client.py``）。

embedding **不受** AI_PROVIDER 影響，一律維持 Azure text-embedding-3-large（3072 維），
Qdrant collection 與 LangGraph store 的維度都不變；本模組因此只提供對話模型的工廠。

所有對話模型的建立都應經過這裡，避免各檔案各自 if/else：

- LangChain：``get_chat_llm(use_mini=..., temperature=...)``
- 原生 OpenAI SDK 介面（``client.chat.completions.create``）：
  ``get_chat_client(azure_factory)`` + ``get_chat_model_name(azure_resolver)``
"""
from __future__ import annotations

import os
from typing import Any, Callable, TypeVar

AZURE = "azure"
BEDROCK = "bedrock"
SUPPORTED_PROVIDERS = (AZURE, BEDROCK)

_T = TypeVar("_T")


def get_ai_provider() -> str:
    """回傳目前的供應商；未設定時為 azure，設定了不認得的值直接報錯（避免靜默走錯供應商）。"""
    raw = os.getenv("AI_PROVIDER", "").strip().lower()
    if not raw:
        return AZURE
    if raw not in SUPPORTED_PROVIDERS:
        raise RuntimeError(
            f"AI_PROVIDER_INVALID: AI_PROVIDER 只能是 {' 或 '.join(SUPPORTED_PROVIDERS)}，收到 {raw!r}。"
        )
    return raw


def is_bedrock() -> bool:
    return get_ai_provider() == BEDROCK


# ── LangChain 對話模型 ───────────────────────────────────────────────────────

def _make_azure_chat_llm(*, use_mini: bool, temperature: float):
    from langchain_openai import AzureChatOpenAI

    from app.pdf_config import pdf_settings

    deployment = (
        pdf_settings.azure_mini_deployment
        if use_mini and pdf_settings.azure_mini_deployment
        else pdf_settings.azure_chat_deployment
    )
    return AzureChatOpenAI(
        azure_deployment=deployment,
        azure_endpoint=pdf_settings.azure_openai_endpoint,
        api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
        api_version=pdf_settings.azure_openai_api_version,
        temperature=temperature,
    )


def get_chat_llm(*, use_mini: bool = False, temperature: float):
    """回傳 LangChain chat model。

    - azure：``AzureChatOpenAI``；``use_mini`` 且有設定 ``AZURE_MINI_DEPLOYMENT`` 時用 mini 部署，
      否則用 ``AZURE_CHAT_DEPLOYMENT``（設定來自 ``app.pdf_config.pdf_settings``）。
    - bedrock：``ChatBedrockConverse``；``use_mini`` 用 ``BEDROCK_MINI_MODEL_ID``。
    """
    if is_bedrock():
        from app.services.bedrock_client import make_chat_llm

        return make_chat_llm(use_mini=use_mini, temperature=temperature)
    return _make_azure_chat_llm(use_mini=use_mini, temperature=temperature)


def disable_parallel_tool_calls(llm):
    """讓 agent 一次只呼叫一個工具。

    azure 沿用 ``bind(parallel_tool_calls=False)``；Bedrock Converse 沒有對應參數
    （ChatBedrockConverse 收到會直接拋 TypeError），所以 bedrock 直接回傳原模型。
    """
    if is_bedrock():
        return llm
    return llm.bind(parallel_tool_calls=False)


# ── 原生 OpenAI SDK 介面 ─────────────────────────────────────────────────────

def get_chat_client(azure_factory: Callable[[], _T]) -> _T | Any:
    """回傳支援 ``client.chat.completions.create(...)`` 的 client。

    azure 時呼叫端原本建立 client 的函式（``azure_factory``）原封不動執行；
    bedrock 時回傳 ``BedrockOpenAI`` 轉接器（只支援 chat.completions，不支援 embeddings）。
    """
    if is_bedrock():
        from app.services.bedrock_client import get_openai_compatible_client

        return get_openai_compatible_client()
    return azure_factory()


def get_chat_model_name(azure_resolver: Callable[[], str], *, use_mini: bool = False) -> str:
    """回傳要傳給 ``chat.completions.create(model=...)`` 的模型名稱。"""
    if is_bedrock():
        from app.services.bedrock_client import chat_model_id, mini_model_id

        return mini_model_id() if use_mini else chat_model_id()
    return azure_resolver()


# ── 工具 ─────────────────────────────────────────────────────────────────────

def message_text(content: Any) -> str:
    """把 LangChain message 的 content 轉成純文字。

    Azure 回傳字串，原樣回傳；ChatBedrockConverse 串流時 content 是 content block 的 list
    （例如 ``[{"type": "text", "text": "..."}]``，工具呼叫則是 ``tool_use`` block），只取文字部分。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)
