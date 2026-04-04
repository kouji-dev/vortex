#!/usr/bin/env bash
# Start the E2E stack (./scripts/e2e-up.sh) in the background, wait until /health
# responds, then run Playwright from frontend/. Use SKIP_E2E_STACK=1 if the API
# is already up.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ "${SKIP_E2E_STACK:-}" = "1" ]; then
  exec pnpm --dir frontend test:e2e "$@"
fi

./scripts/e2e-up.sh &
UP_PID=$!

cleanup() {
  kill "$UP_PID" 2>/dev/null || true
  pkill -f "uvicorn ai_portal.main:app.*8001" 2>/dev/null || true
}
trap cleanup EXIT

BASE="${E2E_API_URL:-http://127.0.0.1:8001}"
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
