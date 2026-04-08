# AI Portal — Project Rules for Claude

## Testing Workflow (Non-Negotiable)

After implementing any feature or fix, the task is NOT done until:

1. E2E Playwright tests are written for the new functionality
2. New tests pass: `pnpm test:e2e:filter <spec-name>`
3. All tests pass: `pnpm test:e2e`
4. If tests fail, keep iterating — do not mark the task complete until all tests are green

**E2E tests MUST ALWAYS run against the E2E database. NEVER the dev database.**

### E2E DB Isolation (CRITICAL — Never Violate)

- Dev backend: port **8000**, DB `ai_portal` on container `local-dev-ai-portal-db` (port 5434)
- E2E backend: port **8001**, DB `ai_portal_e2e` on container `local-e2e-ai-portal-db` (port 5435)

These MUST NEVER mix. Running E2E tests while the dev backend occupies port 8001 corrupts the dev DB.

**Before running any E2E tests:**
1. Ensure dev backend is on port 8000 (check `API_PORT=8000` in `.env`)
2. Start E2E backend: `./scripts/e2e-up.sh` from the repo root (resets E2E DB, runs migrations)
3. Verify: `curl http://localhost:8001/health` — must show `ai_portal_e2e` DB in startup logs

**If multiple uvicorn processes are running on port 8001**, kill them all before running e2e-up.sh:
```bash
wmic process where "commandline like '%uvicorn%' and commandline like '%8001%'" call terminate
```

**After a worktree is deleted**, always delete `.worktree.env` from the repo root — stale worktree ports cause E2E tests to hit the wrong backend.

## E2E Scripts (frontend/)

| Command | Purpose |
|---|---|
| `pnpm test:e2e` | Run all E2E tests |
| `pnpm test:e2e:filter <pattern>` | Run a subset by grep pattern, e.g. `pnpm test:e2e:filter thinking-block` |
| `pnpm test:e2e:ui` | Open Playwright UI mode |

Playwright config: **8 workers minimum, 0 retries**.

## E2E Test Principles

- **All E2E interactions must go through the browser UI** — no direct backend API calls in tests, ever
- No E2E seed endpoints exist on the backend — do not create them; do not call them
- Use `createOrFindConversation(page, name)` and `createOrFindKb(page, name)` helpers from `e2e/support/ui-helpers.ts`
- Tests that need isolation use unique names: `` `E2E Isolated ${Date.now()}` ``
- Tests that can share state use a stable name: `"E2E Shared Conversation"`
- To mock streaming/SSE responses use `page.route()` — intercept at the browser level, never seed via API
- Teardown cleanup (e.g. deleting a created resource) may use API calls in `finally` blocks — only the regular app API, never seed-specific endpoints

## Worktree Isolation

When working in a git worktree, each worktree gets its own isolated environment:
- Dedicated Postgres containers (dev DB + E2E DB)
- Unique ports for backend, E2E backend, frontend, E2E frontend
- All config flows through a `.worktree.env` file at the repo root (gitignored)

### Worktree Scripts

```bash
# Set up a new worktree environment (creates DBs, runs migrations + seed)
./scripts/worktree-up.sh <worktree-name>

# Tear down a worktree environment (stops/removes Docker containers, frees ports)
./scripts/worktree-down.sh <worktree-name>
```

### Port Registry

`.worktrees.json` (repo root, gitignored) tracks assigned port ranges:
```json
{
  "main": { "apiPort": 8001, "e2eApiPort": 8011, "frontendPort": 5173, "e2eFrontendPort": 5175, "dbPort": 5434, "e2eDbPort": 5435 },
  "feature-xyz": { "apiPort": 8002, "e2eApiPort": 8012, "frontendPort": 5176, "e2eFrontendPort": 5177, "dbPort": 5436, "e2eDbPort": 5437 }
}
```

### Config Flow

```
.worktrees.json  (registry, gitignored)
     ↓ written by worktree-up.sh
.worktree.env    (per-worktree, gitignored)
     ↓ sourced by e2e-up.sh, uvicorn start, vite start
backend/config.py       ← DATABASE_URL, API_PORT
frontend/vite.config.ts ← VITE_DEV_API_PROXY_TARGET
playwright.config.ts    ← E2E_API_URL, E2E_BASE_URL
```

`.worktree.env` example:
```
WORKTREE_NAME=feature-xyz
API_PORT=8002
E2E_API_PORT=8012
FRONTEND_PORT=5176
E2E_FRONTEND_PORT=5177
DB_PORT=5436
E2E_DB_PORT=5437
DB_NAME=ai_portal_feature_xyz
E2E_DB_NAME=ai_portal_e2e_feature_xyz
```

Both `worktree-up.sh` and `worktree-down.sh` are **idempotent**:
- `worktree-up.sh`: if DB already exists, skip creation and just re-run migrations
- `worktree-down.sh`: if container not found, skip silently

## Running the App

Always start with `--host` to expose on the local network:
```bash
pnpm dev --host
```
Print the network IP URL (e.g. `http://192.168.1.99:5173`) so it can be opened on mobile.
