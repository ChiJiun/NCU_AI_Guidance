"""PDF 問答的結構化輸出 schema 與 LangGraph store 維度檢查的測試（不需要網路／AWS）。"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("AWS_ACCESS_KEY_ID", "x")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "x")
os.environ.setdefault("BEDROCK_CHAT_MODEL_ID", "fake-chat")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


def _schema_models():
    from app.agents.pdf.router_agent import RouterDecision
    from app.agents.pdf.runner import AgentResponse
    from app.agents.pdf.research import planner, reflector, scheduler, task_planner, writer

    models = [AgentResponse, RouterDecision]
    for module, name in [
        (planner, "PlannerDecision"), (reflector, "Reflection"), (scheduler, "SchedulerDecision"),
        (task_planner, "ResearchPlan"), (writer, "ResearchStructuredWriteup"),
    ]:
        models.append(getattr(module, name))
    return models


def test_structured_output_schemas_use_only_supported_keywords():
    problems = {}
    for model in _schema_models():
        bad = _violations(model.model_json_schema())
        if bad:
            problems[model.__name__] = bad
    assert not problems, f"以下 schema 含 Bedrock 結構化輸出不支援的約束：{problems}"


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    async def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, row, fail=False):
        self._row, self._fail = row, fail

    async def execute(self, _sql):
        if self._fail:
            raise RuntimeError("db down")
        return _FakeCursor(self._row)


class _FakePool:
    def __init__(self, row, fail=False):
        self._conn = _FakeConn(row, fail)

    def connection(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()


def test_store_dim_mismatch_logs_error_with_migration_sql(caplog):
    from app.agents.pdf import runner

    with caplog.at_level(logging.ERROR, logger=runner.logger.name):
        actual = asyncio.run(runner.check_store_vector_dims(_FakePool((3072,)), 1024))
    assert actual == 3072
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "3072" in text and "1024" in text and "TRUNCATE store_vectors" in text


def test_store_dim_match_is_silent(caplog):
    from app.agents.pdf import runner

    with caplog.at_level(logging.WARNING, logger=runner.logger.name):
        assert asyncio.run(runner.check_store_vector_dims(_FakePool({"atttypmod": 1024}), 1024)) == 1024
    assert not caplog.records


@pytest.mark.parametrize("pool", [_FakePool(None), _FakePool((1,), fail=True)])
def test_store_dim_unknown_returns_none(pool):
    from app.agents.pdf import runner

    assert asyncio.run(runner.check_store_vector_dims(pool, 1024)) is None


def test_violation_scanner_catches_max_items():
    from pydantic import BaseModel, Field

    class Bad(BaseModel):
        sources: list[str] = Field(default_factory=list, max_length=3)

    assert any("maxItems" in v for v in _violations(Bad.model_json_schema()))
