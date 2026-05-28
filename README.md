# AI Portal

**Status:** 5-module enterprise AI suite — feature-complete, smoke-tested.

Self-hosted AI control plane for regulated EU enterprises. Five modules, one substrate:

- **Control Plane** — orgs, users, SSO, SCIM, RBAC, API keys, audit, usage, billing, webhooks, settings, module flags
- **Gateway** — provider-compatible APIs (OpenAI/Anthropic/Bedrock), routing, failover, rate limits, prompt caching, guardrails, traces
- **RAG Management** — KBs, connectors, ingestion, embedders, vector stores, hybrid search, rerank, eval
- **Memories** — user/conversation/team memories, BYOK encryption, extraction, recall, decay, GDPR cascade
- **Task Workers** — sandboxed coding agents, git/issue triggers, live streaming, M-of-N approvals, replay

Control Plane is the only hard dependency; the other four are independently toggleable per org via `module_flags`. Architecture: [`docs/superpowers/specs/2026-05-28-suite-overview-design.md`](docs/superpowers/specs/2026-05-28-suite-overview-design.md). Per-module specs: [`docs/superpowers/specs/2026-05-28-*-design.md`](docs/superpowers/specs/).

---

## Quick start

```bash
# 1. Clone + install
git clone <repo> ai-portal && cd ai-portal
pnpm install

# 2. Start Postgres (pgvector) + Redis
docker compose up -d

# 3. Configure backend env
cp server/api/.env.example server/api/.env
# Generate keys:
#   SECRET_KEY:  python -c "import secrets; print(secrets.token_hex(32))"
#   AUDIT_KEK:   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   MEMORY_KEK:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# For dev without real provider keys: set GATEWAY_USE_FAKE_PROVIDER=true

# 4. Run migrations
cd server/api
alembic upgrade head

# 5. Boot backend (port 8000)
python -m uvicorn ai_portal.main:app --port 8000 --reload

# 6. Boot frontend (port 5173)
cd ../../apps/frontend
pnpm dev --host

# 7. Login
# Open http://localhost:5173
# Dev mode: bearer token `devtoken` (see DEV_BEARER_TOKEN in .env)
# First signup = org owner
```

Verify: `curl http://localhost:8000/health` — startup logs name the DB.

---

## Docs

- **Operator runbook** — [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — env vars, bootstrap, failure modes, module flags, smoke tests, E2E
- **Architecture specs** — [`docs/superpowers/specs/`](docs/superpowers/specs/) — per-module designs, suite overview
- **Pivot (historical)** — [`Pivot.md`](Pivot.md) — phase-based plan, superseded by suite-overview spec
- **Backend** — [`server/api/README.md`](server/api/README.md)
- **Frontend E2E** — [`apps/frontend/e2e/README.md`](apps/frontend/e2e/README.md)

---

## Ports (dev)

| Service | Port |
|---|---|
| Dev backend | 8000 |
| E2E backend | 8001 |
| Dev frontend | 5173 |
| E2E frontend | 5175 |
| Dev DB (Postgres + pgvector) | 5434 |
| E2E DB | 5435 |
| Redis | 6380 |

Worktree ports tracked in `.worktrees.json` (gitignored). See [`docs/RUNBOOK.md`](docs/RUNBOOK.md#worktree-isolation).

---

## Deployment

Render + Supabase blueprint in [`render.yaml`](render.yaml). Self-hosted single-org mode: set `DEPLOYMENT_MODE=selfhosted` — first boot serves `/setup` wizard.
