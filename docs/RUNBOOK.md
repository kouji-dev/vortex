# AI Portal — Operator Runbook

Bootstrap, env, failure modes, module toggles, smoke tests, E2E.

---

## Required env vars

Set in `server/api/.env` (gitignored). Copy from `server/api/.env.example` and fill.

### Core (always required)

| Var | What | How to generate / set |
|---|---|---|
| `DATABASE_URL` | Postgres URL with pgvector | Dev: `postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal` |
| `SECRET_KEY` | App secret — sessions, CSRF, signed cookies | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `AUDIT_KEK` | Fernet KEK — envelope-encrypts audit payloads | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `MEMORY_KEK` | Fernet KEK — envelope-encrypts memory BYOK ciphertext | Same Fernet cmd as above |

`SECRET_KEY` is required when `DEPLOYMENT_MODE in (saas, selfhosted)`. KEKs required when audit/memory encryption enabled (default on).

### Modes + deployment

| Var | Values | Default | Purpose |
|---|---|---|---|
| `AUTH_MODE` | `dev` \| `entra` | `dev` | `dev` = fixed bearer + seed user; `entra` = JWT validation + app roles |
| `DEPLOYMENT_MODE` | `dev` \| `saas` \| `selfhosted` | `dev` | `selfhosted` = single-org, first boot serves `/setup` wizard |
| `OTEL_ENABLED` | `true` \| `false` | `false` | OTLP exporter + auto-instrumentation |
| `CATALOG_SYNC_ENABLED` | `true` \| `false` | `false` | Background model-catalog refresh + provider health probes |

### Gateway (dev / test without real keys)

| Var | Values | Purpose |
|---|---|---|
| `GATEWAY_USE_FAKE_PROVIDER` | `true` \| `false` | Binds `FakeProvider` to compat routes — required to run gateway smoke tests, dev demos, E2E without real provider creds |

When false and no real routing wired, `/v1/chat/completions` raises `no provider configured`.

### Optional integrations

| Var | Purpose |
|---|---|
| `SENDGRID_API_KEY` | Notify provider for login alerts, invites, password reset (falls back to SMTP) |
| `STRIPE_API_KEY` | Billing provider; `STRIPE_WEBHOOK_SECRET` for webhook signature verify |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | Real LLM creds — only needed when not using fake provider |
| `VOYAGE_API_KEY` | Voyage embedder |
| `TAVILY_API_KEY` / `SERPER_API_KEY` / `EXA_API_KEY` / `FIRECRAWL_API_KEY` / `JINA_API_KEY` | Search + scrape providers |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | Email fallback |
| `LANGFUSE_*` | Trace export |

### E2E only (set by `scripts/e2e-up.sh`)

| Var | Purpose |
|---|---|
| `E2E_ENABLE_RAG_SEED` | Mounts `/api/dev/seed-kb` for RAG-tool E2E specs |
| `E2E_ENABLE_CHAT_MESSAGES_SEED` | Mounts `/api/dev/seed-messages` for chat pagination E2E |

Never enable in prod.

---

## Bootstrap from scratch

```bash
# 1. Bring up infra (Postgres + Redis)
docker compose up -d

# 2. Create the dev DB (auto-created by docker compose entrypoint)
# 3. Create the e2e DB
docker exec local-dev-ai-portal-db createdb -U postgres ai_portal_e2e || true

# 4. Configure env
cp server/api/.env.example server/api/.env
# Edit: generate SECRET_KEY, AUDIT_KEK, MEMORY_KEK (cmds above).
# Set GATEWAY_USE_FAKE_PROVIDER=true if no provider creds.

# 5. Migrations
cd server/api
alembic upgrade head

# 6. (optional) Seed catalog
python -m ai_portal.scripts.seed_catalog_models --skip-model-validation

# 7. Boot backend
python -m uvicorn ai_portal.main:app --port 8000 --reload

# 8. Boot frontend
cd ../../apps/frontend
pnpm install
pnpm dev --host

# 9. Verify
curl http://localhost:8000/health
# → 200; startup logs show DB name + module wiring
```

First user signup auto-grants `owner` role on the new org.

---

## Common failure modes

### `type "X" already exists` during `alembic upgrade head`

Half-applied migration history. Drop and recreate the DB:
```bash
docker exec local-dev-ai-portal-db dropdb -U postgres ai_portal
docker exec local-dev-ai-portal-db createdb -U postgres ai_portal
cd server/api && alembic upgrade head
```

### `value too long for type character varying(32)` on `alembic_version`

Pre-064 migrations missed the column widening. Fix is in `041`/`042` (widen `alembic_version` to `varchar(255)` before long revid branches). Run `alembic upgrade head` on a fresh DB — chain is now green from base to head.

### Backend won't start

- Check `SECRET_KEY` set when `DEPLOYMENT_MODE != dev`
- Check `AUDIT_KEK` + `MEMORY_KEK` set (Fernet keys, base64 32 bytes)
- Check `DATABASE_URL` reachable: `psql $DATABASE_URL -c "SELECT 1"`
- Check no port conflict on `API_PORT` (default 8000)

### 403 on admin routes

- RBAC: caller lacks required permission. First signup auto-grants `owner`. If you've revoked it, re-grant via `roles` table.
- `_require_role` previously had a tuple bug (fixed at `4cec79a`) that locked out admins — pull latest pivot.

### `/v1/chat/completions` returns `no provider configured`

Set `GATEWAY_USE_FAKE_PROVIDER=true` for smoke tests, or wire real provider routing + creds.

---

## Module enable / disable

Each module togglable per-org via `module_flags` table. Known modules:
`gateway`, `rag`, `memories`, `workers`, `assistants`, `chat`, `knowledge_base`.

Toggle from control-plane facade:
```python
from ai_portal.control_plane import set_module_flag
set_module_flag(db, org_id, "workers", enabled=False)
```

Or via admin UI: **Settings → Modules** (control plane).

Disabling a module hides its routes for the org and stops billing/usage events from emitting.

---

## Smoke tests (per module)

Quick golden-path verification. All run against scratch DB.

```bash
cd server/api

# Control Plane — register → login → portal API key → audit emitted
python -m pytest tests/smoke/test_control_plane_smoke.py -v

# Gateway — fake provider, /v1/chat/completions, trace + usage emit
GATEWAY_USE_FAKE_PROVIDER=true python -m pytest tests/smoke/test_gateway_smoke.py -v

# RAG — pre-seeded KB, stubbed embedder, retrieval golden path
python -m pytest tests/smoke/test_rag_smoke.py -v

# Memories — BYOK encrypt persists ciphertext + recall
python -m pytest tests/smoke/test_memory_smoke.py -v

# Workers — task → sandbox → PR open
python -m pytest tests/smoke/test_workers_smoke.py -v
```

All five must be green before tagging a release.

---

## E2E

E2E runs against an **isolated** DB on port **5435**. Never mix with dev DB.

```bash
# From repo root — kills stale 8001 processes, resets E2E DB, runs migrations, boots backend
./scripts/e2e-up.sh
# Leave running.

# In another shell:
cd apps/frontend
pnpm test:e2e                          # full suite
pnpm test:e2e:filter <pattern>         # subset by grep
pnpm test:e2e:ui                       # Playwright UI mode
```

E2E status: **6 / 9 suites passing**. Known-broken: see `apps/frontend/e2e/README.md` for current diff vs. main.

Rules:
- E2E DB only — never the dev DB
- UI-only interactions — no direct backend calls in test bodies (cleanup in `finally` is OK)
- 8 workers, 0 retries

---

## Worktree isolation

For parallel branch work, each worktree owns isolated DBs + ports:

```bash
./scripts/worktree-up.sh <name>     # creates DBs, .worktree.env, runs migrations
./scripts/worktree-down.sh <name>   # tears down containers, frees ports
```

Port registry in `.worktrees.json` (gitignored). Per-worktree config in `.worktree.env` (sourced by uvicorn, vite, playwright).

After deleting a worktree, **delete `.worktree.env`** from the repo root — stale ports cause E2E to hit the wrong backend.
