"""Bedrock 轉接層單元測試（不需要 AWS 憑證，以假的 bedrock-runtime client 驗證）。

執行：cd backend && python -m pytest tests -q
"""
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import bedrock_client as bc  # noqa: E402


class FakeRuntime:
    def __init__(self, converse=None, stream_events=None, embedding=None):
        self._converse = converse
        self._stream_events = stream_events or []
        self._embedding = embedding or [0.1, 0.2, 0.3]
        self.calls: list[tuple[str, dict]] = []

    def converse(self, **kwargs):
        self.calls.append(("converse", kwargs))
        return self._converse

    def converse_stream(self, **kwargs):
        self.calls.append(("converse_stream", kwargs))
        return {"stream": iter(self._stream_events)}

    def invoke_model(self, **kwargs):
        self.calls.append(("invoke_model", kwargs))
        body = json.dumps({"embedding": self._embedding, "inputTextTokenCount": 5}).encode()
        return {"body": io.BytesIO(body)}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "搜尋課程",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        },
    }
]


def test_convert_messages_tool_roundtrip_merges_results_into_one_user_message():
    messages = [
        {"role": "system", "content": "你是助理"},
        {"role": "user", "content": "找 Python 課"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "search_courses", "arguments": '{"q": "python"}'}},
                {"id": "t2", "type": "function", "function": {"name": "search_courses", "arguments": '{"q": "ai"}'}},
            ],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "[1]"},
        {"role": "tool", "tool_call_id": "t2", "content": "[2]"},
    ]
    system, converse = bc.convert_messages(messages)

    assert system == [{"text": "你是助理"}]
    assert [m["role"] for m in converse] == ["user", "assistant", "user"]
    assert converse[1]["content"][0]["toolUse"] == {
        "toolUseId": "t1", "name": "search_courses", "input": {"q": "python"},
    }
    results = converse[2]["content"]
    assert [r["toolResult"]["toolUseId"] for r in results] == ["t1", "t2"]


def test_convert_messages_flatten_tools_when_no_tool_config():
    messages = [
        {"role": "user", "content": "找課"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "t1", "function": {"name": "search_courses", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "結果"},
    ]
    _, converse = bc.convert_messages(messages, flatten_tools=True)
    flat = json.dumps(converse, ensure_ascii=False)
    assert "toolUse" not in flat and "toolResult" not in flat
    assert "search_courses" in flat and "結果" in flat
    assert [m["role"] for m in converse] == ["user", "assistant", "user"]


def test_convert_messages_prepends_user_when_history_starts_with_assistant():
    _, converse = bc.convert_messages(
        [{"role": "assistant", "content": "嗨"}, {"role": "user", "content": "你好"}]
    )
    assert converse[0]["role"] == "user"
    assert converse[1]["role"] == "assistant"


def test_convert_tools_choices():
    assert bc.convert_tools(None, "auto") is None
    assert bc.convert_tools(TOOLS, "none") is None
    cfg = bc.convert_tools(TOOLS, "auto")
    assert cfg["toolChoice"] == {"auto": {}}
    assert cfg["tools"][0]["toolSpec"]["inputSchema"]["json"]["type"] == "object"
    assert bc.convert_tools(TOOLS, "required")["toolChoice"] == {"any": {}}
    forced = bc.convert_tools(TOOLS, {"type": "function", "function": {"name": "search_courses"}})
    assert forced["toolChoice"] == {"tool": {"name": "search_courses"}}


def test_completion_with_tool_call_maps_to_openai_shape():
    fake = FakeRuntime(
        converse={
            "output": {"message": {"role": "assistant", "content": [
                {"text": "我來查"},
                {"toolUse": {"toolUseId": "t1", "name": "search_courses", "input": {"q": "ai"}}},
            ]}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": 12, "outputTokens": 7, "totalTokens": 19},
        }
    )
    client = bc.BedrockOpenAI(runtime=fake)
    resp = client.chat.completions.create(
        model="m", messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "q"}],
        tools=TOOLS, tool_choice="auto", temperature=0.2, max_completion_tokens=300,
    )
    msg = resp.choices[0].message
    assert msg.content == "我來查"
    assert msg.tool_calls[0].id == "t1"
    assert msg.tool_calls[0].function.name == "search_courses"
    assert json.loads(msg.tool_calls[0].function.arguments) == {"q": "ai"}
    assert resp.choices[0].finish_reason == "tool_calls"
    assert (resp.usage.prompt_tokens, resp.usage.completion_tokens) == (12, 7)

    _, kwargs = fake.calls[0]
    assert kwargs["inferenceConfig"] == {"maxTokens": 300, "temperature": 0.2}
    assert kwargs["system"] == [{"text": "s"}]
    assert "toolConfig" in kwargs


def test_completion_without_tools_flattens_tool_history():
    fake = FakeRuntime(
        converse={
            "output": {"message": {"role": "assistant", "content": [{"text": "最終答案"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }
    )
    client = bc.BedrockOpenAI(runtime=fake)
    resp = client.chat.completions.create(
        model="m",
        messages=[
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t1", "function": {"name": "search_courses", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "t1", "content": "r"},
        ],
    )
    assert resp.choices[0].message.content == "最終答案"
    assert resp.choices[0].message.tool_calls is None
    _, kwargs = fake.calls[0]
    assert "toolConfig" not in kwargs
    assert "toolUse" not in json.dumps(kwargs["messages"], ensure_ascii=False)


def test_stream_assembles_text_tool_calls_and_usage():
    events = [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "你"}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "好"}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"contentBlockStart": {"contentBlockIndex": 1, "start": {"toolUse": {"toolUseId": "t1", "name": "search_courses"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": '{"q": '}}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": '"ai"}'}}}},
        {"contentBlockStop": {"contentBlockIndex": 1}},
        {"contentBlockStart": {"contentBlockIndex": 2, "start": {"toolUse": {"toolUseId": "t2", "name": "get_dept_courses"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 2, "delta": {"toolUse": {"input": "{}"}}}},
        {"messageStop": {"stopReason": "tool_use"}},
        {"metadata": {"usage": {"inputTokens": 30, "outputTokens": 9, "totalTokens": 39}}},
    ]
    client = bc.BedrockOpenAI(runtime=FakeRuntime(stream_events=events))
    stream = client.chat.completions.create(
        model="m", messages=[{"role": "user", "content": "q"}], tools=TOOLS,
        tool_choice="auto", stream=True, stream_options={"include_usage": True},
    )

    # 與 llm_service 的累積邏輯相同
    tc_buffer: dict[int, dict] = {}
    content, finish, in_tok, out_tok = [], None, 0, 0
    for chunk in stream:
        if not chunk.choices:
            in_tok += chunk.usage.prompt_tokens
            out_tok += chunk.usage.completion_tokens
            continue
        choice = chunk.choices[0]
        finish = choice.finish_reason or finish
        if choice.delta.tool_calls:
            for tcd in choice.delta.tool_calls:
                buf = tc_buffer.setdefault(tcd.index, {"id": "", "name": "", "arguments": ""})
                if tcd.id:
                    buf["id"] = tcd.id
                if tcd.function.name:
                    buf["name"] += tcd.function.name
                if tcd.function.arguments:
                    buf["arguments"] += tcd.function.arguments
        if choice.delta.content:
            content.append(choice.delta.content)

    assert "".join(content) == "你好"
    assert finish == "tool_calls"
    assert (in_tok, out_tok) == (30, 9)
    assert sorted(tc_buffer) == [0, 1]
    assert tc_buffer[0] == {"id": "t1", "name": "search_courses", "arguments": '{"q": "ai"}'}
    assert tc_buffer[1]["name"] == "get_dept_courses"


def test_embeddings_single_and_batch_preserve_order():
    fake = FakeRuntime(embedding=[0.5] * 4)
    client = bc.BedrockOpenAI(runtime=fake)
    single = client.embeddings.create(model="amazon.titan-embed-text-v2:0", input="hi")
    assert len(single.data) == 1 and single.data[0].embedding == [0.5] * 4
    batch = client.embeddings.create(input=["a", "b", "c"])
    assert [d.index for d in batch.data] == [0, 1, 2]
    assert batch.usage.prompt_tokens == 15

    body = json.loads(fake.calls[0][1]["body"])
    assert body["dimensions"] == 1024 and body["normalize"] is True


def test_config_requires_chat_model(monkeypatch):
    monkeypatch.delenv("BEDROCK_CHAT_MODEL_ID", raising=False)
    with pytest.raises(RuntimeError, match="AI_API_CONFIG_MISSING"):
        bc.chat_model_id()
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", "chat-id")
    assert bc.chat_model_id() == "chat-id"
    monkeypatch.delenv("BEDROCK_MINI_MODEL_ID", raising=False)
    assert bc.mini_model_id() == "chat-id"


def test_titan_v2_rejects_unsupported_dimension(monkeypatch):
    monkeypatch.setenv("BEDROCK_EMBEDDING_DIM", "3072")
    with pytest.raises(RuntimeError, match="1024"):
        bc.embedding_dim()
