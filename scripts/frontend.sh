#!/usr/bin/env bash
# Usage: ./scripts/frontend.sh
# Starts only the frontend dev server, network-exposed (--host).
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"

# Load worktree-specific env if present
if [ -f "$REPO/.worktree.env" ]; then
  # shellcheck source=/dev/null
  source "$REPO/.worktree.env"
fi

FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "==> Starting frontend on port $FRONTEND_PORT (network-exposed)..."
cd "$REPO/apps/frontend"
exec pnpm dev --host --port "$FRONTEND_PORT"
