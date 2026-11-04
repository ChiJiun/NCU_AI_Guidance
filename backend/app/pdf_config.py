"""PDF 問答功能設定（與目標系統共用 Qdrant 與資料庫環境變數；LLM 設定見 services/bedrock_client.py）。"""
import pathlib

from pydantic import SecretStr
from pydantic_settings import BaseSettings

# .env lives at the repo root (two levels above this file: backend/app/ → backend/ → repo root).
_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


class PdfChatSettings(BaseSettings):
    # Qdrant（與目標系統共用同一個 server）
    qdrant_url: str = ""
    qdrant_api_key: SecretStr = SecretStr("")
    pdf_qdrant_collection: str = "reports"

    # Database
    database_url: str = ""

    class Config:
        # Look in repo root first, then CWD as fallback.
        env_file = [str(_REPO_ROOT / ".env"), ".env"]
        extra = "ignore"


pdf_settings = PdfChatSettings()
