"""執行子程序：環境變數控管、輸出遮罩、寫 log。"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Mapping

# 不花錢、不碰外部服務的步驟會拿掉這些環境變數，確保它們不可能意外呼叫付費 API 或寫入正式服務
CREDENTIAL_ENV_PREFIXES = (
    "AZURE_OPENAI_", "OPENAI_", "ANTHROPIC_", "QDRANT_", "CLOUDINARY_", "PDF_QDRANT_",
    "AWS_", "BEDROCK_", "FIREBASE_", "GOOGLE_APPLICATION_",
)
CREDENTIAL_ENV_NAMES = ("DATABASE_URL", "CLAUDE_CODE_OAUTH_TOKEN")

_SECRET_ASSIGN = re.compile(
    r"(?i)([\w.-]*(?:password|passwd|secret|token|api[_-]?key|webhook|credential)[\w.-]*)"
    r"(\s*[:=]\s*)(['\"]?)([^\s'\",]+)"
)
_URL_CREDENTIALS = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)([^/\s:@]+):([^/\s@]+)@")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")


def redact(line: str) -> str:
    """遮掉輸出裡看起來像金鑰、token、密碼的值。"""
    line = _URL_CREDENTIALS.sub(r"\1***:***@", line)
    line = _BEARER.sub(r"\1 ***", line)
    return _SECRET_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}***", line)


def strip_credentials(env: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in env.items()
            if not (k.upper().startswith(CREDENTIAL_ENV_PREFIXES) or k.upper() in CREDENTIAL_ENV_NAMES)}


def load_env_files(root: Path) -> dict[str, str]:
    """讀 repo 的 .env（與 backend/.env）給需要憑證的步驟用。值不會被印出或寫進 log。"""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    merged: dict[str, str] = {}
    for p in (root / "backend" / ".env", root / ".env"):   # 後讀的優先：根目錄 .env 蓋過 backend/.env
        if p.is_file():
            merged.update({k: v for k, v in dotenv_values(p).items() if v is not None})
    return merged


def build_env(base: Mapping[str, str], *, terms: list[str], credentials: Mapping[str, str] | None) -> dict[str, str]:
    """credentials 為 None 代表這個步驟不該碰任何憑證。"""
    if credentials is None:
        env = strip_credentials(base)
    else:
        env = dict(credentials)
        env.update(base)          # shell 已設定的值優先，與 load_dotenv 預設行為一致
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NCU_DATA_TERMS": ",".join(terms),
    })
    return env


def run_logged(argv: list[str], *, cwd: Path, env: Mapping[str, str], log_path: Path,
               echo: Callable[[str], None]) -> int:
    """執行並逐行輸出（已遮罩）到 echo 與 log 檔，回傳 exit code。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"$ {' '.join(argv)}\n")
        try:
            proc = subprocess.Popen(
                argv, cwd=str(cwd), env=dict(env), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
        except OSError as e:
            msg = f"無法執行：{e}"
            log.write(msg + "\n")
            echo(msg)
            return 127
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = redact(raw.rstrip("\r\n"))
            log.write(line + "\n")
            echo(line)
        rc = proc.wait()
        log.write(f"[exit {rc}]\n")
        return rc
