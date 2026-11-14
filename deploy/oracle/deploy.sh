#!/usr/bin/env bash
# /opt/ncu-backend/deploy.sh — 更新並重啟後端（說明見 docs/oracle-vm-deployment.md）
#   ./deploy.sh             拉最新原始碼 → 建置映像 → 重建容器 → 等健康檢查
#   ./deploy.sh --env-only  只重建容器（改了 backend.env 之後用；docker restart 不會重讀 env_file）
#
# 回退到先前的版本：
#   sudo docker image ls ncu-backend                       # 找到舊的 commit 標籤
#   sudo docker tag ncu-backend:<舊 sha> ncu-backend:latest && ./deploy.sh --env-only
#
# 環境變數（選填）可覆寫原始碼來源，例如要部署自己的 fork 或其他分支：
#   SRC_URL=https://github.com/<owner>/<repo>.git SRC_BRANCH=<branch> ./deploy.sh
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/ncu-backend}"
SRC_URL="${SRC_URL:-https://github.com/clairechien0627/ncu_ai_guidance.git}"
SRC_BRANCH="${SRC_BRANCH:-main}"
HEALTH_URL="http://127.0.0.1:8000"

cd "$DEPLOY_DIR"

if [[ "${1:-}" != "--env-only" ]]; then
  if [[ ! -d repo/.git ]]; then
    git init -q repo
  fi
  git -C repo fetch -q --depth 1 "$SRC_URL" "$SRC_BRANCH"
  git -C repo reset -q --hard FETCH_HEAD
  sha=$(git -C repo rev-parse --short HEAD)
  echo "建置 ${sha}（${SRC_URL} ${SRC_BRANCH}）..."
  # repo 根目錄的 Dockerfile 與 .dockerignore；每個版本另外標上 commit 標籤，方便回退
  sudo docker build -q -t "ncu-backend:${sha}" -t ncu-backend:latest repo >/dev/null
fi

# tunnel.env 還沒填 token 時只啟動後端，避免 cloudflared 不斷重啟
services=(backend)
if grep -qE '^TUNNEL_TOKEN=.+' tunnel.env 2>/dev/null; then
  services+=(tunnel)
else
  echo "tunnel.env 尚未設定 TUNNEL_TOKEN，只啟動後端"
fi
sudo docker compose -f compose.yaml up -d --force-recreate "${services[@]}"

echo -n "等待後端啟動"
for _ in $(seq 1 60); do
  if curl -fsS "${HEALTH_URL}/health" >/dev/null 2>&1; then
    echo " OK"
    # /ready 在向量庫與 reranker 預熱完成前會回 503，屬正常；稍後再查一次即可
    curl -sS "${HEALTH_URL}/ready"; echo
    # 只清掉沒有標籤的映像；帶 commit 標籤的舊映像保留給回退用（需要時手動 docker rmi）
    sudo docker image prune -f >/dev/null
    exit 0
  fi
  echo -n "."; sleep 3
done
echo " 逾時，最近的 log："
sudo docker logs --tail 50 ncu-backend
exit 1
