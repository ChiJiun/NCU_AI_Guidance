"""Bedrock 轉接層與 Claude 結構化輸出相容性測試（假的 bedrock-runtime client，不需要 AWS 憑證）。"""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import bedrock_client as bc  # noqa: E402

HAS_LANGCHAIN_AWS = importlib.util.find_spec("langchain_aws") is not None

FAKE_AWS_ENV = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_CONFIG_FILE": os.devnull,
    "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
    "AWS_EC2_METADATA_DISABLED": "true",
    "AI_PROVIDER": "bedrock",
}


class FakeRuntime:
    def __init__(self, converse=None, stream_events=None):
        self._converse = converse
        self._stream_events = stream_events or []
        self.calls: list[tuple[str, dict]] = []

    def converse(self, **kwargs):
        self.calls.append(("converse", kwargs))
        return self._converse

    def converse_stream(self, **kwargs):
        self.calls.append(("converse_stream", kwargs))
        return {"stream": iter(self._stream_events)}


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


class ConvertTest(unittest.TestCase):
    def test_tool_roundtrip_merges_results_into_one_user_message(self):
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
        self.assertEqual(system, [{"text": "你是助理"}])
        self.assertEqual([m["role"] for m in converse], ["user", "assistant", "user"])
        self.assertEqual(
            converse[1]["content"][0]["toolUse"],
            {"toolUseId": "t1", "name": "search_courses", "input": {"q": "python"}},
        )
        self.assertEqual([r["toolResult"]["toolUseId"] for r in converse[2]["content"]], ["t1", "t2"])

    def test_flatten_tools_when_no_tool_config(self):
        messages = [
            {"role": "user", "content": "找課"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "t1", "function": {"name": "search_courses", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "t1", "content": "結果"},
        ]
        _, converse = bc.convert_messages(messages, flatten_tools=True)
        flat = json.dumps(converse, ensure_ascii=False)
        self.assertNotIn("toolUse", flat)
        self.assertNotIn("toolResult", flat)
        self.assertIn("search_courses", flat)
        self.assertIn("結果", flat)
        self.assertEqual([m["role"] for m in converse], ["user", "assistant", "user"])

    def test_prepends_user_when_history_starts_with_assistant(self):
        _, converse = bc.convert_messages(
            [{"role": "assistant", "content": "嗨"}, {"role": "user", "content": "你好"}]
        )
        self.assertEqual([m["role"] for m in converse], ["user", "assistant", "user"])

    def test_convert_tools_choices(self):
        self.assertIsNone(bc.convert_tools(None, "auto"))
        self.assertIsNone(bc.convert_tools(TOOLS, "none"))
        cfg = bc.convert_tools(TOOLS, "auto")
        self.assertEqual(cfg["toolChoice"], {"auto": {}})
        self.assertEqual(cfg["tools"][0]["toolSpec"]["inputSchema"]["json"]["type"], "object")
        self.assertEqual(bc.convert_tools(TOOLS, "required")["toolChoice"], {"any": {}})
        forced = bc.convert_tools(TOOLS, {"type": "function", "function": {"name": "search_courses"}})
        self.assertEqual(forced["toolChoice"], {"tool": {"name": "search_courses"}})


class CompletionsTest(unittest.TestCase):
    def test_completion_with_tool_call_maps_to_openai_shape(self):
        fake = FakeRuntime(converse={
            "output": {"message": {"role": "assistant", "content": [
                {"text": "我來查"},
                {"toolUse": {"toolUseId": "t1", "name": "search_courses", "input": {"q": "ai"}}},
            ]}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": 12, "outputTokens": 7, "totalTokens": 19},
        })
        client = bc.BedrockOpenAI(runtime=fake)
        resp = client.chat.completions.create(
            model="m", messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "q"}],
            tools=TOOLS, tool_choice="auto", temperature=0.2, max_completion_tokens=300,
        )
        msg = resp.choices[0].message
        self.assertEqual(msg.content, "我來查")
        self.assertEqual(msg.tool_calls[0].id, "t1")
        self.assertEqual(msg.tool_calls[0].function.name, "search_courses")
        self.assertEqual(json.loads(msg.tool_calls[0].function.arguments), {"q": "ai"})
        self.assertEqual(resp.choices[0].finish_reason, "tool_calls")
        self.assertEqual((resp.usage.prompt_tokens, resp.usage.completion_tokens), (12, 7))
        _, kwargs = fake.calls[0]
        self.assertEqual(kwargs["inferenceConfig"], {"maxTokens": 300, "temperature": 0.2})
        self.assertEqual(kwargs["system"], [{"text": "s"}])
        self.assertIn("toolConfig", kwargs)

    def test_default_max_tokens_applied_when_caller_omits(self):
        fake = FakeRuntime(converse={
            "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
            "stopReason": "end_turn", "usage": {},
        })
        with mock.patch.dict(os.environ, {"BEDROCK_MAX_TOKENS": "1234"}):
            bc.BedrockOpenAI(runtime=fake).chat.completions.create(
                model="m", messages=[{"role": "user", "content": "q"}]
            )
        self.assertEqual(fake.calls[0][1]["inferenceConfig"], {"maxTokens": 1234})

    def test_completion_without_tools_flattens_tool_history(self):
        fake = FakeRuntime(converse={
            "output": {"message": {"role": "assistant", "content": [{"text": "最終答案"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1},
        })
        resp = bc.BedrockOpenAI(runtime=fake).chat.completions.create(
            model="m",
            messages=[
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "t1", "function": {"name": "search_courses", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "t1", "content": "r"},
            ],
        )
        self.assertEqual(resp.choices[0].message.content, "最終答案")
        self.assertIsNone(resp.choices[0].message.tool_calls)
        _, kwargs = fake.calls[0]
        self.assertNotIn("toolConfig", kwargs)
        self.assertNotIn("toolUse", json.dumps(kwargs["messages"], ensure_ascii=False))

    def test_stream_assembles_text_tool_calls_and_usage(self):
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
        stream = bc.BedrockOpenAI(runtime=FakeRuntime(stream_events=events)).chat.completions.create(
            model="m", messages=[{"role": "user", "content": "q"}], tools=TOOLS,
            tool_choice="auto", stream=True, stream_options={"include_usage": True},
        )
        # 與 llm_service.stream_with_tools 的累積邏輯相同
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
        self.assertEqual("".join(content), "你好")
        self.assertEqual(finish, "tool_calls")
        self.assertEqual((in_tok, out_tok), (30, 9))
        self.assertEqual(sorted(tc_buffer), [0, 1])
        self.assertEqual(tc_buffer[0], {"id": "t1", "name": "search_courses", "arguments": '{"q": "ai"}'})
        self.assertEqual(tc_buffer[1]["name"], "get_dept_courses")

    def test_region_resolution_order(self):
        keys = ("BEDROCK_REGION", "AWS_REGION", "AWS_DEFAULT_REGION")
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in keys:
                os.environ.pop(k, None)
            self.assertEqual(bc.aws_region(), "ap-northeast-1")
            os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
            self.assertEqual(bc.aws_region(), "us-east-1")
            os.environ["AWS_REGION"] = "us-west-2"
            self.assertEqual(bc.aws_region(), "us-west-2")
            os.environ["BEDROCK_REGION"] = "eu-central-1"
            self.assertEqual(bc.aws_region(), "eu-central-1")


# Anthropic structured outputs / strict tool use 不支援這些 JSON Schema 關鍵字
UNSUPPORTED_KEYWORDS = {
    "maxItems", "minLength", "maxLength", "pattern", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "uniqueItems",
}


def _violations(node, path="$"):
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in UNSUPPORTED_KEYWORDS:
                found.append(f"{path}.{key}={value}")
            if key == "minItems" and value not in (0, 1):
                found.append(f"{path}.minItems={value}")
            found.extend(_violations(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            found.extend(_violations(item, f"{path}[{i}]"))
    return found


class StructuredOutputSchemaTest(unittest.TestCase):
    def test_scanner_catches_max_items(self):
        from pydantic import BaseModel, Field

        class Bad(BaseModel):
            sources: list[str] = Field(default_factory=list, max_length=3)

        self.assertTrue(any("maxItems" in v for v in _violations(Bad.model_json_schema())))

    def test_schemas_sent_to_claude_use_only_supported_keywords(self):
        """bedrock 時會送給 Claude 的結構化輸出 schema（with_structured_output / ProviderStrategy）。"""
        from app.agents.pdf.research import planner, reflector, scheduler, task_planner, writer
        from app.agents.pdf.router_agent import RouterDecision
        from app.agents.pdf.runner import BedrockAgentResponse

        models = [
            BedrockAgentResponse, RouterDecision, planner.PlannerDecision, reflector.Reflection,
            scheduler.SchedulerDecision, task_planner.ResearchPlan, writer.ResearchStructuredWriteup,
        ]
        problems = {m.__name__: bad for m in models if (bad := _violations(m.model_json_schema()))}
        self.assertFalse(problems, f"以下 schema 含 Claude 結構化輸出不支援的約束：{problems}")


@unittest.skipUnless(HAS_LANGCHAIN_AWS, "需要 langchain-aws")
class ChatBedrockConverseCompatTest(unittest.TestCase):
    """以假的 runtime client 驗證 ChatBedrockConverse 在本專案用法下的請求格式。"""

    def _llm(self, fake):
        with mock.patch.dict(os.environ, FAKE_AWS_ENV):
            llm = bc.make_chat_llm(temperature=0.3)
        llm.client = fake
        return llm

    def test_provider_strategy_becomes_output_config_without_max_items(self):
        from langchain.agents.structured_output import ProviderStrategy

        from app.agents.pdf.runner import BedrockAgentResponse

        fake = FakeRuntime(converse={
            "output": {"message": {"role": "assistant", "content": [
                {"text": '{"answer": "答案", "sources": []}'}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        })
        llm = self._llm(fake)
        strategy = ProviderStrategy(BedrockAgentResponse, strict=True)
        result = llm.bind(**strategy.to_model_kwargs()).invoke("問題")
        self.assertEqual(json.loads(result.content)["answer"], "答案")
        _, kwargs = fake.calls[0]
        schema = kwargs["outputConfig"]["textFormat"]["structure"]["jsonSchema"]["schema"]
        self.assertNotIn("maxItems", schema)
        self.assertEqual(json.loads(schema)["additionalProperties"], False)
        self.assertEqual(kwargs["inferenceConfig"]["maxTokens"], bc.DEFAULT_MAX_TOKENS)

    def test_with_structured_output_strict_uses_forced_tool(self):
        from app.agents.pdf.router_agent import RouterDecision

        fake = FakeRuntime(converse={
            "output": {"message": {"role": "assistant", "content": [{"toolUse": {
                "toolUseId": "t1", "name": "RouterDecision",
                "input": {"agent_name": "chat", "reason": "閒聊"},
            }}]}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        })
        llm = self._llm(fake)
        out = llm.with_structured_output(RouterDecision, include_raw=True).invoke("嗨")
        self.assertIsInstance(out["parsed"], RouterDecision)
        self.assertEqual(out["parsed"].agent_name, "chat")
        _, kwargs = fake.calls[0]
        self.assertEqual(kwargs["toolConfig"]["toolChoice"], {"tool": {"name": "RouterDecision"}})

    def test_bind_parallel_tool_calls_is_rejected_so_factory_must_skip_it(self):
        """記錄為什麼 disable_parallel_tool_calls() 在 bedrock 不 bind。"""
        fake = FakeRuntime(converse={
            "output": {"message": {"role": "assistant", "content": [{"text": "x"}]}},
            "stopReason": "end_turn", "usage": {},
        })
        with self.assertRaises(TypeError):
            self._llm(fake).bind(parallel_tool_calls=False).invoke("hi")

    def test_stream_chunks_are_block_lists_and_message_text_flattens_them(self):
        from app.services.ai_provider import message_text

        events = [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "你"}}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "好"}}},
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "end_turn"}},
            {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3}, "metrics": {"latencyMs": 1}}},
        ]
        llm = self._llm(FakeRuntime(stream_events=events))
        chunks = list(llm.stream("hi"))
        self.assertTrue(any(isinstance(c.content, list) and c.content for c in chunks))
        self.assertEqual("".join(message_text(c.content) for c in chunks), "你好")


if __name__ == "__main__":
    unittest.main()
