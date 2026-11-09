"""Shared Qdrant connection kwargs for the course retriever and the PDF RAG layer."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "qdrant"}


def qdrant_connection_kwargs(url: str, api_key: str | None, timeout: int) -> dict:
    """Build QdrantClient kwargs.

    Switching .env to the local Docker instance (QDRANT_URL=http://localhost:6333, see
    scripts/qdrant/README.md) while leaving the Cloud QDRANT_API_KEY set makes
    qdrant-client warn "Api key is used with an insecure connection" on every client:
    the key would be sent in plain HTTP. The local container has no auth, so the key is
    dropped for plain-HTTP local hosts. Remote hosts keep the key (and the warning).
    """
    kwargs: dict = {"url": url, "timeout": timeout}
    api_key = (api_key or "").strip()
    if not api_key:
        return kwargs
    parsed = urlparse(url)
    if parsed.scheme == "http" and (parsed.hostname or "") in _LOCAL_HOSTS:
        logger.info("Qdrant: plain-HTTP local URL, not sending QDRANT_API_KEY")
        return kwargs
    kwargs["api_key"] = api_key
    return kwargs
