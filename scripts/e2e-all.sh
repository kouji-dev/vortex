#!/usr/bin/env bash
# Start the E2E stack (./scripts/e2e-up.sh) in the background, wait until /health
# responds, then run Playwright from frontend/. Use SKIP_E2E_STACK=1 if the API
# is already up.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Source .worktree.env so E2E_API_PORT / E2E_FRONTEND_PORT are available
if [ -f "$ROOT/.worktree.env" ]; then
  set -o allexport
  # shellcheck disable=SC1091
  source "$ROOT/.worktree.env"
  set +o allexport
fi

: "${E2E_API_PORT:=8001}"

if [ "${SKIP_E2E_STACK:-}" = "1" ]; then
  exec pnpm --dir frontend test:e2e "$@"
fi

./scripts/e2e-up.sh &
UP_PID=$!

cleanup() {
  kill "$UP_PID" 2>/dev/null || true
  pkill -f "uvicorn ai_portal.main:app.*${E2E_API_PORT}" 2>/dev/null || true
}
trap cleanup EXIT

BASE="${E2E_API_URL:-http://127.0.0.1:${E2E_API_PORT}}"
BASE="${BASE%/}"
deadline=$((SECONDS + 120))
while true; do
  if curl -sf "$BASE/health" >/dev/null 2>&1; then
    break
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "ERROR: E2E API did not become healthy at $BASE/health within 120s." >&2
    exit 1
  fi
  sleep 1
done

pnpm --dir frontend test:e2e "$@"
