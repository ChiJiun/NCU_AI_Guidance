"""AI_PROVIDER 開關的測試（全部用 mock，不打任何雲端 API）。

驗證：
(a) 未設定／azure 時回傳 Azure 型別，且行為與切換前相同；
(b) bedrock 時回傳 Bedrock 型別；
(c) embedding 不論 AI_PROVIDER 都維持 Azure text-embedding-3-large（3072 維）。
"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services import ai_provider  # noqa: E402
from app.services import bedrock_client  # noqa: E402

HAS_LANGCHAIN_AWS = importlib.util.find_spec("langchain_aws") is not None

# 假的 Azure 設定（不是真的金鑰／端點；只用來建構 client 物件，不會發出請求）
FAKE_AZURE_ENV = {
    "AZURE_OPENAI_API_KEY": "test-key",
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
    "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
    "AZURE_OPENAI_CHAT_DEPLOYMENT": "gpt-4o",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-large",
}
# 隔離 boto3：不讀使用者的 ~/.aws，也不查 EC2 metadata
FAKE_AWS_ENV = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_CONFIG_FILE": os.devnull,
    "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
    "AWS_EC2_METADATA_DISABLED": "true",
}
BEDROCK_KEYS = ("BEDROCK_REGION", "BEDROCK_CHAT_MODEL_ID", "BEDROCK_MINI_MODEL_ID", "BEDROCK_MAX_TOKENS")


def _env(provider: str | None, **extra):
    """回傳 patch.dict 用的環境；provider=None 代表完全不設定 AI_PROVIDER。"""
    env = dict(FAKE_AZURE_ENV)
    env.update(FAKE_AWS_ENV)
    env.update(extra)
    patcher = mock.patch.dict(os.environ, env)

    class _Ctx:
        def __enter__(self_inner):
            patcher.start()
            for key in ("AI_PROVIDER", *BEDROCK_KEYS):
                if key not in extra:
                    os.environ.pop(key, None)
            if provider is not None:
                os.environ["AI_PROVIDER"] = provider
            return self_inner

        def __exit__(self_inner, *exc):
            patcher.stop()
            return False

    return _Ctx()


def _patch_pdf_settings(mini="gpt-4o-mini"):
    from app.pdf_config import pdf_settings
    from pydantic import SecretStr

    return mock.patch.multiple(
        pdf_settings,
        azure_openai_api_key=SecretStr("test-key"),
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_api_version="2024-12-01-preview",
        azure_chat_deployment="gpt-4o",
        azure_mini_deployment=mini,
        azure_embedding_deployment="text-embedding-3-large",
    )


class ProviderSwitchTest(unittest.TestCase):
    def test_default_is_azure_when_unset_or_blank(self):
        with _env(None):
            self.assertEqual(ai_provider.get_ai_provider(), "azure")
            self.assertFalse(ai_provider.is_bedrock())
        with _env("  "):
            self.assertEqual(ai_provider.get_ai_provider(), "azure")

    def test_case_and_whitespace_insensitive(self):
        with _env(" Bedrock "):
            self.assertEqual(ai_provider.get_ai_provider(), "bedrock")
        with _env("AZURE"):
            self.assertEqual(ai_provider.get_ai_provider(), "azure")

    def test_unknown_value_raises_instead_of_silently_falling_back(self):
        with _env("openai"):
            with self.assertRaisesRegex(RuntimeError, "AI_PROVIDER_INVALID"):
                ai_provider.get_ai_provider()


class LangChainFactoryTest(unittest.TestCase):
    def test_azure_default_returns_azure_chat_openai(self):
        from langchain_openai import AzureChatOpenAI

        with _env(None), _patch_pdf_settings():
            llm = ai_provider.get_chat_llm(temperature=0.3)
            mini = ai_provider.get_chat_llm(use_mini=True, temperature=0)
        self.assertIsInstance(llm, AzureChatOpenAI)
        self.assertEqual(llm.deployment_name, "gpt-4o")
        self.assertEqual(llm.temperature, 0.3)
        self.assertIsInstance(mini, AzureChatOpenAI)
        self.assertEqual(mini.deployment_name, "gpt-4o-mini")

    def test_azure_mini_falls_back_to_chat_deployment_when_unset(self):
        with _env("azure"), _patch_pdf_settings(mini=""):
            mini = ai_provider.get_chat_llm(use_mini=True, temperature=0)
        self.assertEqual(mini.deployment_name, "gpt-4o")

    def test_azure_binds_parallel_tool_calls_false(self):
        from langchain_core.runnables import RunnableBinding

        with _env(None), _patch_pdf_settings():
            llm = ai_provider.get_chat_llm(temperature=0.3)
            bound = ai_provider.disable_parallel_tool_calls(llm)
        self.assertIsInstance(bound, RunnableBinding)
        self.assertEqual(bound.kwargs, {"parallel_tool_calls": False})

    @unittest.skipUnless(HAS_LANGCHAIN_AWS, "需要 langchain-aws")
    def test_bedrock_returns_chat_bedrock_converse(self):
        from langchain_aws import ChatBedrockConverse

        with _env("bedrock"):
            llm = ai_provider.get_chat_llm(temperature=0.2)
            mini = ai_provider.get_chat_llm(use_mini=True, temperature=0)
            same = ai_provider.disable_parallel_tool_calls(llm)
        self.assertIsInstance(llm, ChatBedrockConverse)
        self.assertEqual(llm.model_id, bedrock_client.DEFAULT_CHAT_MODEL_ID)
        self.assertEqual(llm.region_name, bedrock_client.DEFAULT_REGION)
        self.assertEqual(llm.temperature, 0.2)
        self.assertEqual(llm.max_tokens, bedrock_client.DEFAULT_MAX_TOKENS)
        self.assertFalse(llm.disable_streaming)
        self.assertIsInstance(mini, ChatBedrockConverse)
        self.assertEqual(mini.model_id, bedrock_client.DEFAULT_MINI_MODEL_ID)
        # Converse 不支援 parallel_tool_calls，bedrock 不應 bind
        self.assertIs(same, llm)

    @unittest.skipUnless(HAS_LANGCHAIN_AWS, "需要 langchain-aws")
    def test_bedrock_model_settings_from_env(self):
        with _env(
            "bedrock",
            BEDROCK_REGION="us-west-2",
            BEDROCK_CHAT_MODEL_ID="us.anthropic.claude-sonnet-4-6",
            BEDROCK_MINI_MODEL_ID="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            BEDROCK_MAX_TOKENS="4096",
        ):
            llm = ai_provider.get_chat_llm(temperature=0)
            mini = ai_provider.get_chat_llm(use_mini=True, temperature=0)
        self.assertEqual(llm.model_id, "us.anthropic.claude-sonnet-4-6")
        self.assertEqual(llm.region_name, "us-west-2")
        self.assertEqual(llm.max_tokens, 4096)
        self.assertEqual(mini.model_id, "us.anthropic.claude-haiku-4-5-20251001-v1:0")

    def test_invalid_max_tokens_raises(self):
        with _env("bedrock", BEDROCK_MAX_TOKENS="abc"):
            with self.assertRaisesRegex(RuntimeError, "BEDROCK_MAX_TOKENS"):
                bedrock_client.default_max_tokens()
        with _env("bedrock", BEDROCK_MAX_TOKENS="0"):
            with self.assertRaisesRegex(RuntimeError, "BEDROCK_MAX_TOKENS"):
                bedrock_client.default_max_tokens()


class NativeClientFactoryTest(unittest.TestCase):
    def test_azure_calls_original_factory(self):
        sentinel = object()
        factory = mock.Mock(return_value=sentinel)
        with _env(None):
            self.assertIs(ai_provider.get_chat_client(factory), sentinel)
            self.assertEqual(ai_provider.get_chat_model_name(lambda: "gpt-4o"), "gpt-4o")
        factory.assert_called_once_with()

    def test_bedrock_returns_adapter_and_never_calls_azure_factory(self):
        factory = mock.Mock(side_effect=AssertionError("azure factory must not be called"))
        with _env("bedrock"):
            client = ai_provider.get_chat_client(factory)
            self.assertEqual(ai_provider.get_chat_model_name(lambda: "gpt-4o"), bedrock_client.DEFAULT_CHAT_MODEL_ID)
            self.assertEqual(
                ai_provider.get_chat_model_name(lambda: "gpt-4o", use_mini=True),
                bedrock_client.DEFAULT_MINI_MODEL_ID,
            )
        self.assertIsInstance(client, bedrock_client.BedrockOpenAI)
        self.assertFalse(hasattr(client, "embeddings"), "Bedrock 轉接器不應提供 embedding")
        factory.assert_not_called()

    def test_llm_service_chat_client_follows_provider(self):
        from app.services import llm_service as llm

        azure_client = object()
        with mock.patch.object(llm, "_get_client", return_value=azure_client) as get_client:
            with _env(None):
                self.assertIs(llm._get_chat_client(), azure_client)
                os.environ.pop("AZURE_OPENAI_CHAT_DEPLOYMENT", None)
                self.assertEqual(llm._chat_deployment(), "gpt-4o")
            with _env("bedrock"):
                self.assertIsInstance(llm._get_chat_client(), bedrock_client.BedrockOpenAI)
                self.assertEqual(llm._chat_deployment(), bedrock_client.DEFAULT_CHAT_MODEL_ID)
        get_client.assert_called_once_with()

    def test_llm_service_generate_answer_through_bedrock_adapter(self):
        from app.services import llm_service as llm

        runtime = mock.Mock()
        runtime.converse.return_value = {
            "output": {"message": {"role": "assistant", "content": [{"text": "建議修資料結構"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        }
        adapter = bedrock_client.BedrockOpenAI(runtime=runtime)
        with _env("bedrock"), \
                mock.patch.object(llm, "_get_client", side_effect=AssertionError("不應建立 Azure client")), \
                mock.patch.object(bedrock_client, "get_openai_compatible_client", return_value=adapter):
            result = llm.generate_answer("要修什麼課？")
        self.assertEqual(result["answer"], "建議修資料結構")
        self.assertEqual(result["model"], bedrock_client.DEFAULT_CHAT_MODEL_ID)
        self.assertEqual((result["input_tokens"], result["output_tokens"]), (10, 5))
        kwargs = runtime.converse.call_args.kwargs
        self.assertEqual(kwargs["modelId"], bedrock_client.DEFAULT_CHAT_MODEL_ID)
        self.assertEqual(kwargs["inferenceConfig"]["maxTokens"], llm.MAX_TOKENS)

    def test_course_question_chat_uses_bedrock_but_keeps_azure_client_for_embedding(self):
        from app.services import course_info_service as cis

        runtime = mock.Mock()
        runtime.converse.return_value = {
            "output": {"message": {"role": "assistant", "content": [{"text": "這門課教排序"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }
        adapter = bedrock_client.BedrockOpenAI(runtime=runtime)
        with _env("bedrock"), \
                mock.patch.object(cis, "build_course_context", return_value=("課程脈絡", [])), \
                mock.patch.object(cis, "_get_ai_client", side_effect=AssertionError("對話不應走 Azure")), \
                mock.patch.object(bedrock_client, "get_openai_compatible_client", return_value=adapter):
            result = cis.answer_course_question("CE1001", "這門課教什麼？")
        self.assertEqual(result["answer"], "這門課教排序")
        self.assertEqual(result["model"], bedrock_client.DEFAULT_CHAT_MODEL_ID)
        self.assertEqual(runtime.converse.call_args.kwargs["inferenceConfig"], {"maxTokens": 800, "temperature": 0.2})

    def test_course_question_azure_path_unchanged(self):
        from app.services import course_info_service as cis

        azure_client = mock.Mock()
        azure_client.chat.completions.create.return_value = mock.Mock(
            choices=[mock.Mock(message=mock.Mock(content=" 答案 "))]
        )
        with _env(None), \
                mock.patch.object(cis, "build_course_context", return_value=("課程脈絡", [])), \
                mock.patch.object(cis, "_get_ai_client", return_value=azure_client), \
                mock.patch.object(bedrock_client, "get_openai_compatible_client",
                                  side_effect=AssertionError("azure 模式不應建立 Bedrock client")):
            result = cis.answer_course_question("CE1001", "這門課教什麼？")
        self.assertEqual(result, {"answer": "答案", "model": "gpt-4o", "warnings": []})
        self.assertEqual(azure_client.chat.completions.create.call_args.kwargs["model"], "gpt-4o")


class EmbeddingUnaffectedTest(unittest.TestCase):
    """(c) embedding 一律維持 Azure text-embedding-3-large / 3072 維。"""

    def test_rag_dense_embeddings_stay_azure(self):
        from langchain_openai import AzureOpenAIEmbeddings

        from app import rag

        for provider in (None, "azure", "bedrock"):
            with self.subTest(provider=provider), _env(provider), _patch_pdf_settings(), \
                    mock.patch.object(rag, "_dense_embeddings", None):
                emb = rag.get_dense_embeddings()
                self.assertIsInstance(emb, AzureOpenAIEmbeddings)
                self.assertEqual(emb.deployment, "text-embedding-3-large")

    def test_course_info_and_retriever_embed_with_azure_client(self):
        from app.services import course_info_service as cis
        from app.services import retriever

        self.assertEqual(cis.VECTOR_DIM, 3072)
        for provider in (None, "bedrock"):
            with self.subTest(provider=provider), _env(provider), \
                    mock.patch.object(bedrock_client, "get_openai_compatible_client",
                                      side_effect=AssertionError("embedding 不應走 Bedrock")):
                azure = mock.Mock()
                azure.embeddings.create.return_value = mock.Mock(data=[mock.Mock(embedding=[0.1] * 3072)])
                with mock.patch.object(cis, "_get_ai_client", return_value=azure):
                    vec = cis._embed_query.__wrapped__("程式設計")
                self.assertEqual(len(vec), 3072)
                self.assertEqual(azure.embeddings.create.call_args.kwargs["model"], "text-embedding-3-large")

                oai = mock.Mock()
                oai.embeddings.create.return_value = mock.Mock(data=[mock.Mock(embedding=[0.2] * 3072)])
                with mock.patch.object(retriever, "_get_oai", return_value=oai):
                    self.assertEqual(len(retriever._embed.__wrapped__("程式設計")), 3072)
                self.assertEqual(oai.embeddings.create.call_args.kwargs["model"], "text-embedding-3-large")


class RunnerSetupTest(unittest.TestCase):
    """PDF 問答 agent 的建構：LangGraph store 維度、結構化輸出 schema、parallel_tool_calls。"""

    def _run_setup(self, provider):
        import psycopg_pool

        from app.agents.pdf import runner

        llm = mock.MagicMock(name="llm")
        pool = mock.MagicMock()
        pool.open = mock.AsyncMock()
        saver = mock.MagicMock()
        saver.return_value.setup = mock.AsyncMock()
        store = mock.MagicMock()
        store.return_value.setup = mock.AsyncMock()
        create_agent = mock.MagicMock(return_value="agent")
        resets = {name: None for name in (
            "_llm", "_agent_llm", "_mini_llm", "_mini_agent_llm",
            "_checkpointer", "_store", "_tool_agent", "_tool_agent_mini", "_pool",
        )}
        with _env(provider), _patch_pdf_settings(), \
                mock.patch.multiple(runner, **resets), \
                mock.patch.object(psycopg_pool, "AsyncConnectionPool", return_value=pool), \
                mock.patch.object(runner, "AsyncPostgresSaver", saver), \
                mock.patch.object(runner, "AsyncPostgresStore", store), \
                mock.patch.object(runner, "create_agent", create_agent), \
                mock.patch.object(runner, "set_query_expander_llm"), \
                mock.patch.object(runner, "get_chat_llm", return_value=llm) as get_chat_llm:
            asyncio.run(runner.setup_checkpointer())
        return runner, llm, saver, store, create_agent, get_chat_llm

    def test_store_embedding_is_azure_3072_for_every_provider(self):
        from langchain_openai import AzureOpenAIEmbeddings

        for provider in (None, "bedrock"):
            with self.subTest(provider=provider):
                _, _, _, store, _, _ = self._run_setup(provider)
                index = store.call_args.kwargs["index"]
                self.assertEqual(index["dims"], 3072)
                self.assertIsInstance(index["embed"], AzureOpenAIEmbeddings)
                self.assertEqual(index["embed"].deployment, "text-embedding-3-large")

    def test_azure_keeps_original_schema_and_parallel_bind(self):
        runner, llm, saver, _, create_agent, get_chat_llm = self._run_setup(None)
        schemas = {c.kwargs["response_format"].schema for c in create_agent.call_args_list}
        self.assertEqual(schemas, {runner.AgentResponse})
        self.assertEqual(runner.AgentResponse.model_json_schema()["properties"]["sources"]["maxItems"], 3)
        llm.bind.assert_called_with(parallel_tool_calls=False)
        get_chat_llm.assert_any_call(temperature=0.3)
        get_chat_llm.assert_any_call(use_mini=True, temperature=0.3)

    def test_bedrock_uses_schema_without_max_items_and_no_parallel_bind(self):
        runner, llm, saver, _, create_agent, _ = self._run_setup("bedrock")
        schemas = {c.kwargs["response_format"].schema for c in create_agent.call_args_list}
        self.assertEqual(schemas, {runner.BedrockAgentResponse})
        self.assertTrue(issubclass(runner.BedrockAgentResponse, runner.AgentResponse))
        bedrock_schema = runner.BedrockAgentResponse.model_json_schema()
        azure_schema = runner.AgentResponse.model_json_schema()
        self.assertNotIn("maxItems", json.dumps(bedrock_schema))
        # 除了 maxItems 與 title 外，送給模型的 schema 與 azure 版完全相同（沒有多出 description 等）
        del azure_schema["properties"]["sources"]["maxItems"]
        for schema in (azure_schema, bedrock_schema):
            schema.pop("title")
        self.assertEqual(bedrock_schema, azure_schema)
        llm.bind.assert_not_called()
        # agent 直接用原本的 LLM（沒有 bind）
        agent_llms = [c.args[0] for c in create_agent.call_args_list]
        self.assertTrue(all(a is llm for a in agent_llms))


class ContentTextTest(unittest.TestCase):
    def test_message_text_handles_str_and_bedrock_blocks(self):
        self.assertEqual(ai_provider.message_text("hello"), "hello")
        self.assertEqual(ai_provider.message_text(None), "")
        self.assertEqual(ai_provider.message_text([]), "")
        self.assertEqual(
            ai_provider.message_text([
                {"type": "text", "text": "你", "index": 0},
                {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
                {"type": "text", "text": "好"},
            ]),
            "你好",
        )


class LazyImportTest(unittest.TestCase):
    """azure 模式不應載入 langchain_aws / bedrock_client（不需要 AWS 套件與憑證也能啟動）。"""

    def test_azure_mode_does_not_import_bedrock_modules(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(BACKEND)!r})\n"
            "import app.services.llm_service, app.services.course_info_service\n"
            "import app.agents.pdf.router_agent, app.agents.pdf.runner, app.agents.pdf.chat_agent\n"
            "import app.agents.pdf.research.agent, app.tools.search_core\n"
            "from app.services.ai_provider import get_chat_llm, get_chat_client\n"
            "llm = get_chat_llm(temperature=0)\n"
            "print(type(llm).__name__)\n"
            "print('langchain_aws' in sys.modules, 'app.services.bedrock_client' in sys.modules)\n"
        )
        env = {k: v for k, v in os.environ.items() if k != "AI_PROVIDER"}
        env.update(FAKE_AZURE_ENV)
        env.update({"AZURE_CHAT_DEPLOYMENT": "gpt-4o", "AZURE_MINI_DEPLOYMENT": "gpt-4o-mini"})
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=str(ROOT / "tests"), env=env,
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
        lines = proc.stdout.strip().splitlines()
        self.assertEqual(lines[-2], "AzureChatOpenAI")
        self.assertEqual(lines[-1], "False False")


if __name__ == "__main__":
    unittest.main()
