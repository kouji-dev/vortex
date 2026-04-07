#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# worktree-down.sh  —  Tear down an isolated worktree environment.
#
# What it does:
#   1. Stops and removes the dev + E2E Postgres Docker containers.
#   2. Removes the worktree entry from .worktrees.json (frees the port slot).
#   3. Removes .worktree.env if it belongs to this worktree.
#
# Idempotent: safe to run even if containers / entries are already gone.
#
# Usage:
#   ./scripts/worktree-down.sh <worktree-name>
#   ./scripts/worktree-down.sh          # reads WORKTREE_NAME from .worktree.env
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKTREES_JSON="$REPO_ROOT/.worktrees.json"
WORKTREE_ENV="$REPO_ROOT/.worktree.env"

# ── Resolve name ──────────────────────────────────────────────────────────────
NAME="${1:-}"
if [ -z "$NAME" ] && [ -f "$WORKTREE_ENV" ]; then
  NAME=$(grep '^WORKTREE_NAME=' "$WORKTREE_ENV" 2>/dev/null | cut -d= -f2 || true)
fi

if [ -z "$NAME" ]; then
  echo "Usage: $0 <worktree-name>" >&2
  echo "  Or run from a directory that contains .worktree.env" >&2
  exit 1
fi

echo "▶ Tearing down worktree '${NAME}'..."

# ── Stop + remove Docker containers ──────────────────────────────────────────
remove_container() {
  local cname="$1"
  if docker inspect "$cname" &>/dev/null; then
    echo "   Stopping $cname..."
    docker stop "$cname" > /dev/null 2>&1 || true
    docker rm   "$cname" > /dev/null 2>&1 || true
    echo "   Removed $cname."
  else
    echo "   $cname not found — skipping."
  fi
}

remove_container "local-ai-portal-db-${NAME}"
remove_container "local-e2e-ai-portal-db-${NAME}"

# ── Remove from .worktrees.json ───────────────────────────────────────────────
if [ -f "$WORKTREES_JSON" ]; then
  python3 - "$WORKTREES_JSON" "$NAME" << 'PYEOF'
import json, sys
path, name = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)
registry = data.get("registry", {})
if name in registry:
    del registry[name]
    data["registry"] = registry
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"   Freed slot for '{name}' in .worktrees.json.")
else:
    print(f"   '{name}' not in .worktrees.json — skipping.")
PYEOF
else
  echo "   .worktrees.json not found — skipping registry update."
fi

# ── Remove .worktree.env ──────────────────────────────────────────────────────
if [ -f "$WORKTREE_ENV" ]; then
  ENV_NAME=$(grep '^WORKTREE_NAME=' "$WORKTREE_ENV" 2>/dev/null | cut -d= -f2 || echo "")
  if [ "$ENV_NAME" = "$NAME" ]; then
    rm "$WORKTREE_ENV"
    echo "   Removed .worktree.env."
  else
    echo "   .worktree.env belongs to '${ENV_NAME}', not '${NAME}' — leaving intact."
  fi
fi

echo "✓ Worktree '${NAME}' torn down."
