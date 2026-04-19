#!/usr/bin/env bash
# Usage: ./scripts/backend.sh
# Starts only the backend dev server on port 8000.
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"

# Load worktree-specific env if present
if [ -f "$REPO/.worktree.env" ]; then
  # shellcheck source=/dev/null
  source "$REPO/.worktree.env"
fi

API_PORT="${API_PORT:-8000}"

echo "==> Starting backend on port $API_PORT..."
cd "$REPO/backend"
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
exec uvicorn src.ai_portal.main:app --port "$API_PORT" --reload
