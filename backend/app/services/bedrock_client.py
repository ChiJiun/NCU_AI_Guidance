"""Amazon Bedrock 存取層。

提供兩種用法：

1. ``get_ai_client()``：回傳一個「長得像 OpenAI SDK」的轉接器，支援
   ``client.chat.completions.create(...)``（含 tools、串流、usage）與
   ``client.embeddings.create(...)``，底層走 Bedrock Converse / Titan Embeddings。
   既有直接呼叫 OpenAI SDK 的程式（llm_service、retriever、course_info_service）
   只需要換掉 client，不用重寫工具呼叫與串流邏輯。
2. ``make_chat_llm()`` / ``make_embeddings()``：給 LangChain（PDF 問答）使用的
   ``ChatBedrockConverse`` / ``BedrockEmbeddings`` 工廠。

環境變數：

- ``AWS_REGION``（或 ``BEDROCK_REGION``）：預設 ap-northeast-1
- ``BEDROCK_CHAT_MODEL_ID``：主要對話模型（必填，例如 APAC inference profile ID）
- ``BEDROCK_MINI_MODEL_ID``：輕量模型（router 等）；未設定時沿用 chat 模型
- ``BEDROCK_EMBEDDING_MODEL_ID``：預設 amazon.titan-embed-text-v2:0
- ``BEDROCK_EMBEDDING_DIM``：預設 1024（Titan V2 只支援 256 / 512 / 1024）

憑證不放在環境變數：ECS 上使用 task role，本機使用 AWS CLI profile / SSO。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from types import SimpleNamespace
from typing import Any, Iterator

logger = logging.getLogger(__name__)

DEFAULT_REGION = "ap-northeast-1"
DEFAULT_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
DEFAULT_EMBEDDING_DIM = 1024
_TITAN_V2_DIMS = (256, 512, 1024)

CONFIG_MISSING_PREFIX = "AI_API_CONFIG_MISSING"


# ── 設定 ─────────────────────────────────────────────────────────────────────

def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def aws_region() -> str:
    return _env("BEDROCK_REGION") or _env("AWS_REGION") or _env("AWS_DEFAULT_REGION") or DEFAULT_REGION


def chat_model_id() -> str:
    model_id = _env("BEDROCK_CHAT_MODEL_ID")
    if not model_id:
        raise RuntimeError(f"{CONFIG_MISSING_PREFIX}: 請設定 BEDROCK_CHAT_MODEL_ID。")
    return model_id


def mini_model_id() -> str:
    return _env("BEDROCK_MINI_MODEL_ID") or chat_model_id()


def embedding_model_id() -> str:
    return _env("BEDROCK_EMBEDDING_MODEL_ID") or DEFAULT_EMBEDDING_MODEL_ID


def embedding_dim() -> int:
    raw = _env("BEDROCK_EMBEDDING_DIM")
    dim = int(raw) if raw else DEFAULT_EMBEDDING_DIM
    if embedding_model_id().startswith("amazon.titan-embed-text-v2") and dim not in _TITAN_V2_DIMS:
        raise RuntimeError(
            f"{CONFIG_MISSING_PREFIX}: Titan Text Embeddings V2 只支援維度 {_TITAN_V2_DIMS}，收到 {dim}。"
        )
    return dim


def _botocore_config():
    from botocore.config import Config

    return Config(
        region_name=aws_region(),
        connect_timeout=10,
        # 研究型 agent 的單次生成可能很久，讀取逾時要比 ALB idle timeout 內的串流寬鬆
        read_timeout=300,
        retries={"max_attempts": 4, "mode": "adaptive"},
    )


@lru_cache(maxsize=1)
def get_runtime_client():
    """boto3 bedrock-runtime client（thread-safe，整個 process 共用一個）。"""
    import boto3

    return boto3.client("bedrock-runtime", config=_botocore_config())


# ── OpenAI 格式 → Converse 格式 ──────────────────────────────────────────────

def _text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type", "text") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)
    return str(content)


def convert_messages(
    messages: list[dict], *, flatten_tools: bool = False
) -> tuple[list[dict], list[dict]]:
    """把 OpenAI chat messages 轉成 Converse 的 (system, messages)。

    - system / developer 訊息合併成 system blocks。
    - assistant 的 tool_calls → toolUse；role=tool → user 訊息中的 toolResult。
    - Converse 要求 user/assistant 交替，連續同 role 的訊息會合併成同一則。
    - ``flatten_tools=True``：歷史中有工具呼叫、但這次呼叫沒有帶 tools 時
      （Converse 規定有 toolUse/toolResult 就必須有 toolConfig），改把工具紀錄轉成純文字。
    """
    system: list[dict] = []
    out: list[dict] = []
    tool_names: dict[str, str] = {}

    def push(role: str, blocks: list[dict]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages:
        role = m.get("role")
        if role in ("system", "developer"):
            text = _text_of(m.get("content"))
            if text.strip():
                system.append({"text": text})
        elif role == "user":
            text = _text_of(m.get("content"))
            if text.strip():
                push("user", [{"text": text}])
        elif role == "assistant":
            blocks: list[dict] = []
            text = _text_of(m.get("content"))
            if text.strip():
                blocks.append({"text": text})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments") or "{}"
                tool_names[tc["id"]] = name
                if flatten_tools:
                    blocks.append({"text": f"[呼叫工具 {name}，參數 {raw_args}]"})
                    continue
                try:
                    parsed = json.loads(raw_args)
                except (TypeError, ValueError):
                    parsed = {}
                if not isinstance(parsed, dict):
                    parsed = {"value": parsed}
                blocks.append({"toolUse": {"toolUseId": tc["id"], "name": name, "input": parsed}})
            push("assistant", blocks)
        elif role == "tool":
            tool_id = m.get("tool_call_id", "")
            text = _text_of(m.get("content")) or "(empty)"
            if flatten_tools:
                label = tool_names.get(tool_id, tool_id)
                push("user", [{"text": f"[工具 {label} 的回傳結果]\n{text}"}])
            else:
                push("user", [{"toolResult": {"toolUseId": tool_id, "content": [{"text": text}]}}])

    # Claude 要求第一則訊息必須是 user
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"text": "(對話開始)"}]})
    return system, out


def _has_tool_blocks(messages: list[dict]) -> bool:
    return any(m.get("role") == "tool" or m.get("tool_calls") for m in messages)


def convert_tools(tools: list[dict] | None, tool_choice: Any) -> dict | None:
    """OpenAI function tools → Converse toolConfig；tool_choice="none" 或沒有 tools 回傳 None。"""
    if not tools or tool_choice == "none":
        return None
    specs = []
    for tool in tools:
        fn = tool.get("function", tool)
        specs.append(
            {
                "toolSpec": {
                    "name": fn["name"],
                    "description": fn.get("description") or fn["name"],
                    "inputSchema": {"json": fn.get("parameters") or {"type": "object", "properties": {}}},
                }
            }
        )
    config: dict[str, Any] = {"tools": specs}
    if tool_choice == "required":
        config["toolChoice"] = {"any": {}}
    elif isinstance(tool_choice, dict) and tool_choice.get("function", {}).get("name"):
        config["toolChoice"] = {"tool": {"name": tool_choice["function"]["name"]}}
    else:
        config["toolChoice"] = {"auto": {}}
    return config


_FINISH_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "content_filtered": "content_filter",
    "guardrail_intervened": "content_filter",
}


def _finish_reason(stop_reason: str | None) -> str | None:
    if stop_reason is None:
        return None
    return _FINISH_REASONS.get(stop_reason, "stop")


def _usage(raw: dict | None) -> SimpleNamespace:
    raw = raw or {}
    prompt = int(raw.get("inputTokens", 0) or 0)
    completion = int(raw.get("outputTokens", 0) or 0)
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=int(raw.get("totalTokens", prompt + completion) or 0),
    )


# ── OpenAI 風格的 client ─────────────────────────────────────────────────────

class _Completions:
    def __init__(self, owner: "BedrockOpenAI") -> None:
        self._owner = owner

    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        stream: bool = False,
        stream_options: dict | None = None,  # noqa: ARG002  Converse 串流一律附帶 usage
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        max_tokens: int | None = None,
        **ignored: Any,
    ):
        if ignored:
            logger.warning("Bedrock 轉接層忽略不支援的參數：%s", sorted(ignored))

        tool_config = convert_tools(tools, tool_choice)
        system, converse_messages = convert_messages(
            messages, flatten_tools=tool_config is None and _has_tool_blocks(messages)
        )
        kwargs: dict[str, Any] = {"modelId": model, "messages": converse_messages}
        if system:
            kwargs["system"] = system
        inference: dict[str, Any] = {}
        limit = max_completion_tokens or max_tokens
        if limit:
            inference["maxTokens"] = int(limit)
        if temperature is not None:
            inference["temperature"] = float(temperature)
        if inference:
            kwargs["inferenceConfig"] = inference
        if tool_config:
            kwargs["toolConfig"] = tool_config

        client = self._owner.runtime
        if stream:
            return self._stream(client, kwargs)
        return self._complete(client, kwargs, model)

    @staticmethod
    def _complete(client, kwargs: dict, model: str) -> SimpleNamespace:
        resp = client.converse(**kwargs)
        message = resp["output"]["message"]
        text_parts: list[str] = []
        tool_calls: list[SimpleNamespace] = []
        for block in message.get("content", []):
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(
                    SimpleNamespace(
                        id=tu["toolUseId"],
                        type="function",
                        function=SimpleNamespace(
                            name=tu["name"],
                            arguments=json.dumps(tu.get("input") or {}, ensure_ascii=False),
                        ),
                    )
                )
        return SimpleNamespace(
            model=model,
            choices=[
                SimpleNamespace(
                    index=0,
                    finish_reason=_finish_reason(resp.get("stopReason")),
                    message=SimpleNamespace(
                        role="assistant",
                        content="".join(text_parts) or None,
                        tool_calls=tool_calls or None,
                    ),
                )
            ],
            usage=_usage(resp.get("usage")),
        )

    @staticmethod
    def _chunk(*, content=None, tool_calls=None, finish_reason=None) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    index=0,
                    finish_reason=finish_reason,
                    delta=SimpleNamespace(role="assistant", content=content, tool_calls=tool_calls),
                )
            ],
            usage=None,
        )

    def _stream(self, client, kwargs: dict) -> Iterator[SimpleNamespace]:
        resp = client.converse_stream(**kwargs)
        tool_slot: dict[int, int] = {}  # contentBlockIndex → OpenAI tool_calls index
        for event in resp["stream"]:
            if "contentBlockStart" in event:
                start = event["contentBlockStart"]
                tool_use = (start.get("start") or {}).get("toolUse")
                if tool_use:
                    slot = len(tool_slot)
                    tool_slot[start["contentBlockIndex"]] = slot
                    yield self._chunk(
                        tool_calls=[
                            SimpleNamespace(
                                index=slot,
                                id=tool_use["toolUseId"],
                                type="function",
                                function=SimpleNamespace(name=tool_use["name"], arguments=""),
                            )
                        ]
                    )
            elif "contentBlockDelta" in event:
                payload = event["contentBlockDelta"]
                delta = payload.get("delta") or {}
                if delta.get("text"):
                    yield self._chunk(content=delta["text"])
                elif "toolUse" in delta:
                    slot = tool_slot.get(payload["contentBlockIndex"])
                    if slot is not None:
                        yield self._chunk(
                            tool_calls=[
                                SimpleNamespace(
                                    index=slot,
                                    id=None,
                                    type=None,
                                    function=SimpleNamespace(
                                        name=None, arguments=delta["toolUse"].get("input", "")
                                    ),
                                )
                            ]
                        )
            elif "messageStop" in event:
                yield self._chunk(finish_reason=_finish_reason(event["messageStop"].get("stopReason")))
            elif "metadata" in event:
                yield SimpleNamespace(choices=[], usage=_usage(event["metadata"].get("usage")))


class _Embeddings:
    _MAX_WORKERS = 8

    def __init__(self, owner: "BedrockOpenAI") -> None:
        self._owner = owner

    def create(
        self,
        *,
        input: str | list[str],  # noqa: A002  與 OpenAI SDK 參數名稱一致
        model: str | None = None,
        dimensions: int | None = None,
        **_ignored: Any,
    ) -> SimpleNamespace:
        texts = [input] if isinstance(input, str) else list(input)
        model_id = model or embedding_model_id()
        dim = dimensions or embedding_dim()
        client = self._owner.runtime

        def embed_one(text: str) -> tuple[list[float], int]:
            body = {"inputText": text if text.strip() else " ", "dimensions": dim, "normalize": True}
            resp = client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(resp["body"].read())
            return payload["embedding"], int(payload.get("inputTextTokenCount", 0))

        if len(texts) > 1:
            with ThreadPoolExecutor(max_workers=min(self._MAX_WORKERS, len(texts))) as pool:
                results = list(pool.map(embed_one, texts))
        else:
            results = [embed_one(t) for t in texts]

        tokens = sum(t for _, t in results)
        return SimpleNamespace(
            model=model_id,
            data=[SimpleNamespace(index=i, embedding=vec) for i, (vec, _) in enumerate(results)],
            usage=SimpleNamespace(prompt_tokens=tokens, total_tokens=tokens),
        )


class BedrockOpenAI:
    """模仿 ``openai.OpenAI`` 介面的最小子集，底層走 Amazon Bedrock。"""

    def __init__(self, runtime: Any | None = None) -> None:
        self._runtime = runtime
        self.chat = SimpleNamespace(completions=_Completions(self))
        self.embeddings = _Embeddings(self)

    @property
    def runtime(self):
        return self._runtime if self._runtime is not None else get_runtime_client()


_client_lock = threading.Lock()
_client: BedrockOpenAI | None = None


def get_ai_client() -> BedrockOpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = BedrockOpenAI()
    return _client


# ── LangChain 工廠 ───────────────────────────────────────────────────────────

def make_chat_llm(kind: str = "chat", *, temperature: float = 0.3, max_tokens: int | None = None):
    """``kind``：``"chat"`` 為主要模型，``"mini"`` 為輕量模型。回傳 ChatBedrockConverse。"""
    from langchain_aws import ChatBedrockConverse

    model_id = mini_model_id() if kind == "mini" else chat_model_id()
    kwargs: dict[str, Any] = {
        "model": model_id,
        "region_name": aws_region(),
        "temperature": temperature,
        "config": _botocore_config(),
        # Claude 支援串流；LangChain 對不認得的模型 ID 會預設停用串流，這裡明確開啟
        "disable_streaming": False,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return ChatBedrockConverse(**kwargs)


def make_embeddings():
    """LangChain 版 Titan Embeddings（維度與 normalize 與 ``BedrockOpenAI.embeddings`` 一致）。"""
    from langchain_aws import BedrockEmbeddings

    return BedrockEmbeddings(
        model_id=embedding_model_id(),
        region_name=aws_region(),
        model_kwargs={"dimensions": embedding_dim(), "normalize": True},
    )
