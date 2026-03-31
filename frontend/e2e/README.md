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
- Optional — **`E2E_ENABLE_RAG_SEED=1`**: enables `POST /api/chat/conversations/{id}/e2e/seed-rag-assistant` (dev-only) so **`chat-rag-indicator.spec.ts`** can assert the 📚 KB usage control on assistant messages **without calling an LLM**. If unset, that test is **skipped**.

Example (PowerShell):

```powershell
$env:DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e"
$env:AUTH_MODE="dev"
$env:DEV_BEARER_TOKEN="devtoken"
$env:DEV_SEED_USER_EMAIL="dev@localhost"
$env:UPLOAD_DIR="C:\path\to\ai-portal\.e2e-uploads"
$env:E2E_ENABLE_RAG_SEED="1"
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

Uploads return **HTTP 200** once the file is stored. Ingest then sets document `status` to **`ready`** or **`failed`**; the UI refreshes the documents table in both cases.

- **Default KB test** waits until the row shows **`ready` or `failed`** (without an embedding key you usually see **`failed`**).
- **Strict ingest test** (optional): set **`E2E_REQUIRE_INGEST_READY=1`** when running Playwright **and** start the API with a working **`OPENAI_API_KEY`** so embeddings succeed; that test asserts **`ready`** only (it is skipped if the env flag is not set).
