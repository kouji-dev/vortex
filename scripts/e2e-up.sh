#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# e2e-up.sh  —  Spin up the isolated E2E backend on port 8001.
#
# What it does:
#   1. Starts the E2E Postgres container (port 5435, db ai_portal_e2e).
#   2. Waits until Postgres is ready.
#   3. Runs alembic migrations (seeds dev user automatically).
#   4. Seeds catalog models (needed for the model-select UI).
#   5. Starts uvicorn on port 8001 pointing at the E2E database.
#
# Prerequisites:
#   - Docker running
#   - Python venv active  (cd backend && pip install -e ".[dev]")
#   - LLM API keys in .env (ANTHROPIC_API_KEY / LLM_API_KEY) — only needed
#     for the chat interaction tests; other tests run without them.
#
# Usage:
#   ./scripts/e2e-up.sh                # foreground — Ctrl-C to stop
#   ./scripts/e2e-up.sh &              # background
#   cd frontend && pnpm e2e            # run Playwright in another shell
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
E2E_DB_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e"

# ── 1. Start the E2E Postgres ─────────────────────────────────────────────
echo "▶ Starting E2E Postgres (port 5435)…"
docker compose -f "$REPO_ROOT/docker-compose.e2e.yml" up -d

# ── 2. Wait for Postgres to be ready ─────────────────────────────────────
echo "▶ Waiting for Postgres to be ready…"
for i in $(seq 1 30); do
  if docker exec local-e2e-ai-portal-db pg_isready -U postgres -d ai_portal_e2e -q 2>/dev/null; then
    echo "   Postgres ready after ${i}s."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "   ERROR: Postgres did not become ready in 30s." >&2
    exit 1
  fi
  sleep 1
done

# ── 3. Run migrations ────────────────────────────────────────────────────
echo "▶ Running alembic migrations…"
(cd "$REPO_ROOT/backend" && DATABASE_URL="$E2E_DB_URL" alembic upgrade head)

# ── 4. Seed catalog models ────────────────────────────────────────────────
# Load LLM keys from the root .env so seed-catalog-models can validate them.
echo "▶ Seeding catalog models…"
if [ -f "$REPO_ROOT/.env" ]; then
  set -o allexport
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +o allexport
fi
(cd "$REPO_ROOT/backend" && DATABASE_URL="$E2E_DB_URL" seed-catalog-models)

# ── 5. Start the API on port 8001 ────────────────────────────────────────
echo "▶ Starting API on http://127.0.0.1:8001 (E2E database)…"
echo "   Press Ctrl-C to stop."
(
  cd "$REPO_ROOT/backend"
  # Re-export all vars from root .env, then override the DB URL and port.
  if [ -f "$REPO_ROOT/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +o allexport
  fi
  export DATABASE_URL="$E2E_DB_URL"
  export API_PORT=8001
  export CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
  uvicorn ai_portal.main:app --host 127.0.0.1 --port 8001 --reload
)
