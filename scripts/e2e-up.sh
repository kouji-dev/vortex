#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# e2e-up.sh  —  Spin up the isolated E2E backend.
#
# What it does:
#   1. Sources .worktree.env if present (worktree-aware ports/DB names).
#   2. Starts the E2E Postgres container (or verifies it's running).
#   3. Waits until Postgres is ready.
#   4. Runs alembic migrations (seeds dev user automatically).
#   5. Seeds catalog models (needed for the model-select UI).
#   6. Starts uvicorn on E2E_API_PORT pointing at the E2E database.
#
# Default ports (main branch, no .worktree.env):
#   Postgres : 5435  db: ai_portal_e2e
#   API      : 8001
#
# Worktree mode (when .worktree.env is present):
#   Ports/DB names come from .worktree.env — set by scripts/worktree-up.sh.
#   The Postgres container is already running; this script skips creation.
#
# Prerequisites:
#   - Docker running
#   - Python venv active  (cd backend && pip install -e ".[dev]")
#   - LLM API keys in .env — only needed for chat interaction tests.
#
# Usage:
#   ./scripts/e2e-up.sh                # foreground — Ctrl-C to stop
#   ./scripts/e2e-up.sh &              # background
#   cd apps/frontend && pnpm test:e2e  # run Playwright in another shell
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── 1. Source .worktree.env if present ───────────────────────────────────────
if [ -f "$REPO_ROOT/.worktree.env" ]; then
  echo "▶ Loading .worktree.env..."
  set -o allexport
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.worktree.env"
  set +o allexport
fi

# Apply defaults for main-branch (no .worktree.env) runs
: "${E2E_DB_PORT:=5435}"
: "${E2E_DB_NAME:=ai_portal_e2e}"
: "${E2E_API_PORT:=8001}"
: "${E2E_FRONTEND_PORT:=5175}"
: "${WORKTREE_NAME:=}"

E2E_DB_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:${E2E_DB_PORT}/${E2E_DB_NAME}"

# ── No paid calls in E2E ────────────────────────────────────────────────────
# Drop real provider keys so the E2E server can't make a real LLM/embedding
# call (the .env sourcing below would otherwise leak them into uvicorn + seed).
# E2E specs mock every provider response in the browser via page.route; with no
# key, anything un-mocked fails loud instead of spending. Catalog seed runs with
# --skip-model-validation so model-select still populates.
_strip_provider_keys() {
  unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY VOYAGE_API_KEY COHERE_API_KEY
}

# Container name: worktree-specific or the default compose name
if [ -n "$WORKTREE_NAME" ]; then
  E2E_CONTAINER="local-e2e-ai-portal-db-${WORKTREE_NAME}"
else
  E2E_CONTAINER="local-e2e-ai-portal-db"
fi

# ── Resolve Python ────────────────────────────────────────────────────────────
if [ -z "${PYTHON:-}" ]; then
  for _candidate in python python3; do
    if command -v "$_candidate" &>/dev/null && "$_candidate" -c "import alembic" &>/dev/null; then
      PYTHON="$_candidate"
      break
    fi
  done
  if [ -z "${PYTHON:-}" ]; then
    echo "ERROR: Could not find a Python with alembic installed." >&2
    echo "  Activate your venv or set PYTHON=/path/to/python and retry." >&2
    exit 1
  fi
fi

# ── 2. Start E2E Postgres ─────────────────────────────────────────────────────
if [ -n "$WORKTREE_NAME" ]; then
  # Worktree mode: container should already be running from worktree-up.sh
  echo "▶ Worktree mode — verifying E2E Postgres (${E2E_CONTAINER})..."
  if ! docker inspect "$E2E_CONTAINER" &>/dev/null; then
    echo "   ERROR: container '$E2E_CONTAINER' not found." >&2
    echo "   Run ./scripts/worktree-up.sh ${WORKTREE_NAME} first." >&2
    exit 1
  fi
  state=$(docker inspect -f '{{.State.Status}}' "$E2E_CONTAINER")
  if [ "$state" != "running" ]; then
    echo "   Container is $state — starting..."
    docker start "$E2E_CONTAINER" > /dev/null
  fi
else
  # Main mode: use docker-compose
  echo "▶ Starting E2E Postgres (port ${E2E_DB_PORT})..."
  docker compose -f "$REPO_ROOT/docker-compose.e2e.yml" up -d
fi

# ── 3. Wait for Postgres ──────────────────────────────────────────────────────
echo "▶ Waiting for Postgres to be ready..."
for i in $(seq 1 30); do
  if docker exec "$E2E_CONTAINER" pg_isready -U postgres -d "$E2E_DB_NAME" -q 2>/dev/null; then
    echo "   Postgres ready after ${i}s."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "   ERROR: Postgres did not become ready in 30s." >&2
    exit 1
  fi
  sleep 1
done

# ── Resolve API directory (worktree vs main) ─────────────────────────────────
if [ -n "$WORKTREE_NAME" ] && [ -d "$REPO_ROOT/.worktrees/${WORKTREE_NAME}/server/api" ]; then
  BACKEND_DIR="$REPO_ROOT/.worktrees/${WORKTREE_NAME}/server/api"
elif [ -n "$WORKTREE_NAME" ] && [ -d "$REPO_ROOT/.worktrees/${WORKTREE_NAME}/backend" ]; then
  # Legacy layout fallback.
  BACKEND_DIR="$REPO_ROOT/.worktrees/${WORKTREE_NAME}/backend"
else
  BACKEND_DIR="$REPO_ROOT/server/api"
fi

# ── 3.5. Reset E2E database ───────────────────────────────────────────────────
echo "▶ Resetting E2E database '${E2E_DB_NAME}' (drop + recreate for a clean run)..."
# Terminate any existing connections so DROP can succeed
docker exec "$E2E_CONTAINER" psql -U postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${E2E_DB_NAME}' AND pid <> pg_backend_pid();" \
  postgres > /dev/null 2>&1 || true
docker exec "$E2E_CONTAINER" psql -U postgres \
  -c "DROP DATABASE IF EXISTS \"${E2E_DB_NAME}\";" postgres
docker exec "$E2E_CONTAINER" psql -U postgres \
  -c "CREATE DATABASE \"${E2E_DB_NAME}\";" postgres
echo "   Database reset."

# ── 4. Run migrations ─────────────────────────────────────────────────────────
echo "▶ Running alembic migrations..."
(cd "$BACKEND_DIR" && DATABASE_URL="$E2E_DB_URL" "$PYTHON" -m alembic upgrade head)

# ── 5. Seed catalog models ────────────────────────────────────────────────────
echo "▶ Seeding catalog models..."
if [ -f "$REPO_ROOT/.env" ]; then
  set -o allexport
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +o allexport
fi
_strip_provider_keys
(cd "$BACKEND_DIR" && DATABASE_URL="$E2E_DB_URL" \
  "$PYTHON" -m ai_portal.scripts.seed_catalog_models --skip-model-validation)

# ── 6. Start the API ──────────────────────────────────────────────────────────
echo "▶ Starting API on http://127.0.0.1:${E2E_API_PORT} (E2E database)..."
echo "   Press Ctrl-C to stop."
(
  cd "$BACKEND_DIR"
  if [ -f "$REPO_ROOT/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +o allexport
  fi
  _strip_provider_keys
  export DATABASE_URL="$E2E_DB_URL"
  export API_PORT="$E2E_API_PORT"
  export CORS_ORIGINS="http://localhost:${E2E_FRONTEND_PORT},http://127.0.0.1:${E2E_FRONTEND_PORT}"
  export E2E_ENABLE_RAG_SEED=1
  export E2E_ENABLE_CHAT_MESSAGES_SEED=1
  export KB_MAX_FILE_SIZE_MB=1
  "$PYTHON" -m uvicorn ai_portal.main:app --host 127.0.0.1 --port "$E2E_API_PORT" --reload
)
