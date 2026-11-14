# 後端（FastAPI）容器映像。建置 context 必須是 repo 根目錄，因為後端會讀取
# <repo>/data 底下的課程與知識圖譜 JSON（路徑以 backend/app 往上三層推算）。
#
#   docker build -t ncu-ai-guidance-backend .
#   docker run --rm -p 8000:8000 --env-file .env ncu-ai-guidance-backend
#
# 部署方式見 docs/deployment.md（Oracle VM + Cloudflare Tunnel、AWS ECS Fargate）。
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # PDF 問答的 stream lock / cancel / steering 是 process 內狀態，必須單 worker
    WEB_CONCURRENCY=1 \
    PORT=8000

# 保持與 repo 相同的目錄結構：/app/backend、/app/data
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend backend
COPY data data

# 以非 root 使用者執行；fastembed / flashrank 會在執行期把模型下載到暫存目錄（/tmp）
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)"

# 不用 --workers：維持單一 process。--proxy-headers 讓反向代理（ALB、cloudflared）後方拿到正確的
# client IP/scheme；容器的 port 只應暴露給代理（ALB 安全群組、或只綁 127.0.0.1），不要直接對外。
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
