# Local E2E (Playwright)

Runs against a **real** API and Postgres. No GitHub Actions job is required; use this on your machine.

## 1. Start E2E Postgres

From the repo root:

```bash
docker compose -f docker-compose.e2e.yml up -d
```

`DATABASE_URL` for migrations and the API:

`postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e`

## 2. Migrate

```bash
cd backend
set DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e
alembic upgrade head
```

(Use `export` instead of `set` on Unix.)

## 3. API (dev auth)

From `backend/` with the same `DATABASE_URL`, plus:

- `AUTH_MODE=dev`
- `DEV_BEARER_TOKEN=devtoken`
- `DEV_SEED_USER_EMAIL=dev@localhost`
- `UPLOAD_DIR` = absolute or repo-relative path to a folder (e.g. repo root `.e2e-uploads` — create once, gitignored)

Example (PowerShell):

```powershell
$env:DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e"
$env:AUTH_MODE="dev"
$env:DEV_BEARER_TOKEN="devtoken"
$env:DEV_SEED_USER_EMAIL="dev@localhost"
$env:UPLOAD_DIR="C:\path\to\ai-portal\.e2e-uploads"
uvicorn ai_portal.main:app --reload --host 127.0.0.1 --port 8000
```

## 4. Frontend

From `frontend/`:

- `VITE_AUTH_MODE=dev`
- `VITE_DEV_BEARER_TOKEN=devtoken`
- `VITE_API_URL=http://127.0.0.1:8000`

```bash
npm run dev
```

## 5. Run tests

From `frontend/`:

```bash
set E2E_API_URL=http://127.0.0.1:8000
npm run test:e2e
```

Optional UI mode: `npm run test:e2e:ui`

First-time browser binaries: `npx playwright install`

## TanStack Start / hydration

Use `waitUntil: 'networkidle'` (or wait for the client bundle to finish) before clicking UI that depends on React state. Otherwise the first click can run before hydration and the create dialog will not open.

## Ingest / embeddings

Uploads run server-side ingest that calls the embedding API. **With** `LLM_API_KEY` / OpenAI-compatible keys configured, documents typically reach status **`ready`** and the UI shows a table row.

**Without** keys, ingest fails: the API still stores the document as **`failed`** but responds with **HTTP 500**, so the SPA shows an **ingest error alert** instead of refreshing the documents table. The KB E2E spec accepts either a visible row (`ready` / `failed`) or that alert plus verification via **`GET /api/knowledge-bases/{id}/documents`** that `sample-e2e.txt` exists with status **`failed`**.
