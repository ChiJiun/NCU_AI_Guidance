"""Application-wide readiness flags. Set by lifespan; read by routes and health checks."""

pdf_chat_ready: bool = False
rag_ready: bool = False
# 展示模式（DEMO_MODE）刻意跳過 RAG 預熱時為 True；/ready 據此回報 ready 而不是 503
rag_skipped: bool = False
