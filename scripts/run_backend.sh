#!/usr/bin/env bash
# 以 0.0.0.0 启动 FastAPI，允许局域网内其他机器（如另一台电脑上的前端 dev server）访问。
# 用法：在仓库根目录执行 `bash scripts/run_backend.sh`，或直接 `./scripts/run_backend.sh`。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="0.0.0.0"
PORT="8000"

# 优先复用已有虚拟环境（backend/.venv 或根目录 .venv），不存在则假定当前环境已装好依赖
if [ -f "$REPO_ROOT/backend/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/backend/.venv/bin/activate"
elif [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
fi

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
echo "==> FastAPI 启动于 http://${HOST}:${PORT}（局域网访问 http://${LAN_IP:-<本机IP>}:${PORT}）"
cd "$REPO_ROOT/backend"
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
