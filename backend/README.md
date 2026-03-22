# AI Portal API

## Run (dev)

From repo root, with Postgres/Redis up (`docker compose up -d`):

```bash
cd backend
pip install -e ".[dev]"
uvicorn ai_portal.main:app --reload --host 0.0.0.0 --port 8000
```

Env: copy repo root `.env.example` to `.env`. Important keys: `DATABASE_URL`, `REDIS_URL`, `DEV_BEARER_TOKEN`, `DEV_SEED_USER_EMAIL`, `OPENAI_API_KEY` (for chat + embeddings), `UPLOAD_DIR`.

### Microsoft Entra (production-style API auth)

Design: [`docs/superpowers/specs/2026-03-22-auth-entra-design.md`](../docs/superpowers/specs/2026-03-22-auth-entra-design.md).

| Variable | Purpose |
|----------|---------|
| `AUTH_MODE` | `dev` (default): bearer `DEV_BEARER_TOKEN` → seed user. `entra`: validate JWTs for this API. |
| `ENTRA_TENANT_ID` | Entra tenant UUID (directory). |
| `ENTRA_API_AUDIENCE` | Access token `aud` — e.g. `api://<api-app-client-id>` or Application ID URI. |

**App registrations (summary):** SPA: auth code + PKCE, redirect to dev/prod origin. API: expose delegated scope; define app roles if using RBAC. Grant SPA permission to API scope; admin consent.

**Frontend (Vite):** `VITE_AUTH_MODE=entra`, `VITE_ENTRA_SPA_CLIENT_ID`, `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_API_SCOPE` (full scope string). In `dev` mode the UI sends `VITE_DEV_BEARER_TOKEN` (default `devtoken`).

## Celery worker (document ingest)

With Redis up:

```bash
cd backend
celery -A ai_portal.worker worker -l info
```

## Tests

Postgres must be reachable at `DATABASE_URL` for integration tests (`test_chat_roundtrip`, model smoke, etc.). CI runs `alembic upgrade head` then `pytest`.

```bash
cd backend
pytest tests -v
```

## Migrations

Order: `001` (vector extension) → `002_core_catalog` → `003_chat` → `004_rag` → `005_entra_oid` → `006_drop_roles` (removed local `roles` / `user_roles`; app RBAC uses Entra JWT `roles` when `AUTH_MODE=entra`).

```bash
cd backend
alembic upgrade head
```
