#!/usr/bin/env bash
# Usage: ./scripts/dev.sh
# Starts backend (port 8000) + frontend (port 5173, network-exposed) in parallel.
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Starting backend..."
cd "$REPO/backend"
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
uvicorn src.ai_portal.main:app --port 8000 --reload &
BACKEND_PID=$!

echo "==> Starting frontend..."
cd "$REPO/frontend"
pnpm dev --host &
FRONTEND_PID=$!

echo ""
echo "Backend  PID $BACKEND_PID  → http://localhost:8000"
echo "Frontend PID $FRONTEND_PID → http://localhost:5173  (network: check Vite output)"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
