"""
demo_mode.py — 比賽展示版的「訪客展示模式」

設定 `DEMO_MODE=true` 後，後端進入預設拒絕（default deny）模式：
- GET / HEAD / OPTIONS 照常放行。目前沒有任何 GET endpoint 會呼叫付費模型；
  tests/test_demo_mode.py 把現有 GET 路由列成快照，新增 GET 路由時測試會失敗，提醒確認它不呼叫模型。
- 其他方法（POST / PUT / PATCH / DELETE）一律回 403 `LIVE_AI_DISABLED`，
  只有 `_ALLOWED_WRITE_ROUTES` 列出、確定不呼叫模型／embedding 的純計算 endpoint 例外。

用「預設拒絕 + 白名單」而不是「逐一封鎖 AI endpoint」，是為了避免日後新增的 AI endpoint
忘了加封鎖而在公開網站產生費用。新增白名單前，請確認該 endpoint 及其呼叫鏈完全不碰
Bedrock（chat / embeddings）。

`GET /api/demo/status` 讓前端知道目前是否為展示模式。
"""
from __future__ import annotations

import os
import re

from fastapi import APIRouter
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

LIVE_AI_DISABLED_CODE = "LIVE_AI_DISABLED"
LIVE_AI_DISABLED_MESSAGE = "比賽展示版目前不提供即時提問，請瀏覽預先產生的示範案例。"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# (method, path 正規表示式)：展示模式下仍允許、且確定不呼叫模型的寫入型 endpoint
_ALLOWED_WRITE_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"^/api/assessment/submit/?$")),             # 量表計分（純規則）
    ("POST", re.compile(r"^/api/assessment/filter-by-subjects/?$")),  # 學測採計篩選（讀 CSV）
    ("POST", re.compile(r"^/api/course-search/?$")),                  # 關鍵字搜尋（不走向量）
    ("POST", re.compile(r"^/api/chat/course_detail/?$")),             # 讀 course_index.json
)


def is_demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "").strip().lower() in _TRUE_VALUES


def is_request_allowed(method: str, path: str) -> bool:
    """展示模式下這個請求能不能放行（不看 DEMO_MODE 本身）。"""
    method = method.upper()
    if method in _SAFE_METHODS:
        return True
    return any(m == method and pattern.match(path) for m, pattern in _ALLOWED_WRITE_ROUTES)


class DemoModeMiddleware:
    """DEMO_MODE 開啟時擋下所有可能呼叫付費模型的請求。

    寫成純 ASGI middleware（不用 BaseHTTPMiddleware），放行的請求直接交給下一層，
    不會額外包住 SSE 串流的 body 與 client disconnect。每次請求都重新讀環境變數，方便測試。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_demo_mode() and not is_request_allowed(scope["method"], scope["path"]):
            response = JSONResponse(
                status_code=403,
                content={"detail": LIVE_AI_DISABLED_MESSAGE, "code": LIVE_AI_DISABLED_CODE},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


router = APIRouter()


@router.get("/status")
async def demo_status():
    demo = is_demo_mode()
    return {"demo_mode": demo, "live_ai_enabled": not demo}
