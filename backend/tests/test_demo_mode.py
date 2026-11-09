"""訪客展示模式（DEMO_MODE）的測試：確認公開訪客無法觸發任何寫入型／模型 endpoint。"""
import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("AWS_ACCESS_KEY_ID", "x")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "x")
os.environ.setdefault("BEDROCK_CHAT_MODEL_ID", "fake-chat")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import demo_mode  # noqa: E402
from app.main import app  # noqa: E402

ORIGIN = "http://localhost:5173"


@pytest.fixture
def client():
    # 不用 `with TestClient(...)`：不跑 lifespan，避免連資料庫／Qdrant。
    # raise_server_exceptions=False：白名單 endpoint 在測試環境缺資料檔時會 500，
    # 這裡只關心「有沒有被展示模式擋下」。
    return TestClient(app, raise_server_exceptions=False)


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


def _write_routes():
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods - {"GET", "HEAD", "OPTIONS"}:
                yield method, _concrete(route.path)


def test_every_write_route_is_blocked_unless_allowlisted(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    routes = sorted(set(_write_routes()))
    assert routes, "應該至少有一個寫入型 endpoint"
    leaked = []
    for method, path in routes:
        resp = client.request(method, path, json={"question": "hi", "query": "hi"})
        allowed = demo_mode.is_request_allowed(method, path)
        blocked = resp.status_code == 403 and resp.json().get("code") == demo_mode.LIVE_AI_DISABLED_CODE
        if allowed == blocked:
            leaked.append((method, path, resp.status_code))
    assert not leaked, f"展示模式下放行／阻擋不符預期：{leaked}"


# 展示模式會放行所有 GET。這份快照列出目前已確認「不呼叫 Bedrock（chat / embeddings）」的 GET 路由；
# 新增 GET 路由時這個測試會失敗——請先確認新路由整條呼叫鏈都不碰模型，再把它加進來。
# 若新路由會呼叫模型，必須在 app/demo_mode.py 另外封鎖，不能只更新快照。
REVIEWED_GET_ROUTES = {
    "/", "/health", "/ready",
    "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
    "/api/assessment/questions", "/api/assessment/admission-criteria",
    "/api/auth/me",
    "/api/courses", "/api/courses/{course_id}",
    "/api/projects", "/api/projects/analytics", "/api/projects/recent-chats", "/api/projects/{project_id}",
    "/api/projects/{project_id}/conversations", "/api/projects/{project_id}/conversations/{thread_id}/messages",
    "/api/graph/search", "/api/graph/neighborhood", "/api/graph/stats",
    "/api/chat/sessions", "/api/chat/session/{session_id}", "/api/chat/analytics", "/api/chat/tools",
    "/api/curriculum/tree", "/api/curriculum/dept/{dept_id}", "/api/curriculum/notes",
    "/api/curriculum/notes/by-id/{dept_id}", "/api/curriculum/pdf/{dept_id}",
    "/api/monitor/db-stats", "/api/monitor/stats",
    "/api/demo/status",
}


def test_get_routes_match_reviewed_snapshot():
    current = {getattr(r, "path", "") for r in app.routes if "GET" in (getattr(r, "methods", None) or set())}
    added = current - REVIEWED_GET_ROUTES
    assert not added, (
        f"新增了 GET 路由 {sorted(added)}：展示模式會放行所有 GET，請確認它不呼叫模型後再加入 REVIEWED_GET_ROUTES"
    )
    assert not REVIEWED_GET_ROUTES - current, f"快照中有已不存在的路由：{sorted(REVIEWED_GET_ROUTES - current)}"


def test_no_unreviewed_mounts_or_websockets():
    """純 ASGI middleware 只檢查 http scope；Mount 與 websocket 路由不在上面兩個掃描範圍內，這裡另外鎖住。"""
    from starlette.routing import Mount, WebSocketRoute

    mounts = {getattr(r, "path", "") for r in app.routes if isinstance(r, Mount)}
    assert mounts <= {"/pdfs"}, f"新增了 Mount {sorted(mounts - {'/pdfs'})}，請確認展示模式下不會呼叫模型"
    assert not [r for r in app.routes if isinstance(r, WebSocketRoute)], "新增了 websocket 路由，展示模式不會檢查它"


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/chat"),
    ("POST", "/api/chat/stream"),
    ("POST", "/api/courses/semantic-search"),
    ("POST", "/api/courses/abc/ask"),
    ("POST", "/api/projects/p1/chat"),
    ("POST", "/api/projects/p1/chat/stream"),
    ("DELETE", "/api/chat/session/s1"),
])
def test_known_ai_endpoints_are_blocked(client, monkeypatch, method, path):
    monkeypatch.setenv("DEMO_MODE", "1")
    resp = client.request(method, path, json={"question": "hi"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "LIVE_AI_DISABLED"


def test_allowlist_entries_match_real_routes():
    """白名單的每一條都要對應到真實存在的 endpoint，避免路徑改名後白名單默默失效或誤放行。"""
    real = set(_write_routes())
    for method, pattern in demo_mode._ALLOWED_WRITE_ROUTES:
        assert any(m == method and pattern.match(p) for m, p in real), pattern.pattern


def test_allowlisted_endpoint_still_works(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    resp = client.post("/api/chat/course_detail", json={"name": "不存在的課", "code": ""})
    assert resp.status_code == 200


def test_blocked_response_keeps_cors_header(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    resp = client.post("/api/chat", json={"question": "hi"}, headers={"Origin": ORIGIN})
    assert resp.status_code == 403
    assert resp.headers.get("access-control-allow-origin") == ORIGIN


def test_preflight_and_get_pass(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    pre = client.options("/api/chat", headers={
        "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
    })
    assert pre.status_code == 200
    assert client.get("/health").status_code == 200


def test_status_endpoint(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    assert client.get("/api/demo/status").json() == {"demo_mode": True, "live_ai_enabled": False}
    monkeypatch.setenv("DEMO_MODE", "false")
    assert client.get("/api/demo/status").json() == {"demo_mode": False, "live_ai_enabled": True}


def _fake_startup_modules(monkeypatch, warmup_result: bool) -> list[str]:
    """把 lifespan 會 import 的 checkpointer 與 RAG 換成假模組，不連資料庫、不載入模型。

    回傳的 list 會記錄 RAG warmup 有沒有被呼叫。
    """
    import types

    calls: list[str] = []

    async def _noop() -> None:
        return None

    async def _warmup() -> bool:
        calls.append("warmup")
        return warmup_result

    runner = types.ModuleType("app.agents.pdf.runner")
    vars(runner).update(setup_checkpointer=_noop, shutdown_checkpointer=_noop)
    rag = types.ModuleType("app.rag")
    vars(rag).update(warmup=_warmup, close_qdrant_clients=_noop)
    monkeypatch.setitem(sys.modules, "app.agents.pdf.runner", runner)
    monkeypatch.setitem(sys.modules, "app.rag", rag)
    return calls


def test_demo_mode_skips_rag_warmup_and_reports_ready(monkeypatch):
    """展示模式不載入 reranker／向量庫（512 MB 主機會 OOM），/ready 仍要回 200，避免健康檢查判定失敗。"""
    monkeypatch.setenv("DEMO_MODE", "true")
    calls = _fake_startup_modules(monkeypatch, warmup_result=True)
    with TestClient(app) as c:
        assert calls == [], "展示模式不應執行 RAG warmup"
        resp = c.get("/ready")
        assert resp.status_code == 200
        assert resp.json()["rag"] == "skipped"


@pytest.mark.parametrize("warmup_ok,expected_status", [(True, 200), (False, 503)])
def test_normal_mode_still_runs_rag_warmup(monkeypatch, warmup_ok, expected_status):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    calls = _fake_startup_modules(monkeypatch, warmup_result=warmup_ok)
    with TestClient(app) as c:
        assert calls == ["warmup"]
        resp = c.get("/ready")
        assert resp.status_code == expected_status
        if warmup_ok:
            assert resp.json()["rag"] == "ready"


def test_demo_mode_off_does_not_block(client, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    resp = client.post("/api/chat", json={"question": "hi"})
    # 沒登入 → 由原本的認證擋下（401/403 但不是 LIVE_AI_DISABLED）
    assert resp.json().get("code") != "LIVE_AI_DISABLED"
