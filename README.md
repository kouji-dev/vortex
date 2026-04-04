# AI Portal

Self-hosted AI portal. **Capability registry and what is actually in the repo:** [`docs/superpowers/specs/README.md`](docs/superpowers/specs/README.md) (includes an **implementation snapshot** vs brainstorm backlog).

### What is implemented today (short)

- **Backend:** FastAPI — assistants, **conversations** (streaming chat via **LangChain** to OpenAI-compatible and Anthropic APIs), **knowledge bases** (upload, inline ingest worker, pgvector retrieval), **model catalog**, **user profile memories** API, **`/api/me`** and **portal API keys** (`aip_…` when using Entra-oriented settings).
- **Auth:** `AUTH_MODE=dev` (fixed bearer token + seed user) or **`AUTH_MODE=entra`** (JWT validation and app roles). Local dev typically uses `VITE_DEV_TOKEN` / `DEV_BEARER_TOKEN`.
- **Frontend:** TanStack Start — home, **chat** (conversations), **knowledge bases**, **memories** page.
- **Infra:** Docker Compose `local-dev` — Postgres (**pgvector**, port **5434**) and Redis (**6380**); optional **`full`** profile builds API + web.

### What is not (yet) or differs from early MVP docs

- **No Celery** — document ingest runs **on the API request path** (thread offload), not a Redis queue worker.
- **No LiteLLM sidecar** in the default path — models are called via **LangChain** in the API process.
- **No full I-08 entitlements** product layer — RBAC / roles exist; feature gating across the app is not complete.
- **Portal API keys:** REST CRUD exists; a **dedicated “my keys” UI** in the web app is not wired yet.
- **Stretch items** (FinOps dashboards, hybrid search, citations UX, guardrails productization, external KB connectors, etc.) remain in specs as **target**, not current behavior.

Full detail and file pointers: [`docs/superpowers/specs/README.md`](docs/superpowers/specs/README.md). Historical chunk map (checkboxes may be stale): [`docs/superpowers/plans/2026-03-21-ai-portal-mvp-implementation.md`](docs/superpowers/plans/2026-03-21-ai-portal-mvp-implementation.md).

## Local dev — Postgres & Redis (`local-dev`)

Infrastructure follows the same **Docker Compose project name** and layout as **kouji-factory** (`name: local-dev`, postgres + redis, named volumes). See `docker-compose.yml` and compare with `../kouji-factory/docker-compose.yml`.

- **This repo** uses host ports **5434** (Postgres) and **6380** (Redis) so you can run **ai-portal** next to **kouji-factory** (which uses **5433** / **6379**).
- Postgres image is **`pgvector/pgvector:pg17`** so the `vector` extension is available for RAG.

```bash
# Create repo root `.env` (gitignored) — see comments in that file and backend/README.md.
docker compose up -d
docker compose ps
```

Put **`DATABASE_URL`** and other API settings in **`.env`** at the repo root (same directory as `docker-compose.yml`). Compose still includes Redis on **6380** for optional local use or future queues.

After **resetting the DB volume** (`docker compose down -v` then `up -d`), run migrations and the catalog seed from `backend/` — see **“After a database reset”** in [`backend/README.md`](backend/README.md).

## API + web (MVP-0)

- **Backend:** from `backend/`, run Uvicorn on port **8000** (see `backend/README.md`). `CORS_ORIGINS` in `.env` should include **`http://localhost:5173`** (TanStack Start dev server).
- **Frontend:** **`frontend/`** is **TanStack Start** (Vite + `@tanstack/react-start`, TanStack Router file routes, TanStack Query, Tailwind v4). Copy `frontend/.env.example` → `frontend/.env` if you need to override **`VITE_API_URL`** (defaults to `http://127.0.0.1:8000` in code).

```bash
cd frontend
npm install
npm run dev
```

Copy `frontend/.env.example` → `frontend/.env` and set **`VITE_DEV_TOKEN=devtoken`** so catalog/chat routes can call the API.

### VS Code: run API + web together

Tasks live in **`.vscode/tasks.json`**. The backend task uses **Python: Select Interpreter** (`python.defaultInterpreterPath`), so `uvicorn` must be installed in that environment.

1. **`cd backend`** then **`python -m venv .venv`** (or create a venv via the Python extension).
2. **Command Palette → Python: Select Interpreter** → choose **`backend/.venv/...`**.
3. Run task **`backend: pip install (editable dev)`** once (installs `uvicorn` and deps).
4. Run **`Dev: API + Web (watch)`** (or **Run Build Task** / **Ctrl+Shift+B**).

### Full stack in Docker (optional)

With **Postgres** (and optional Redis) already up (`docker compose up -d`), build and run API and web:

```bash
docker compose --profile full build
docker compose --profile full run --rm api alembic upgrade head
docker compose --profile full up -d api web
```

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000) — web UI: [http://127.0.0.1:3000](http://127.0.0.1:3000)  
- Set **`OPENAI_API_KEY`** in `.env` (or the shell) before `up` so chat/embeddings work.

Chat and embeddings use **LangChain** in-process in the API (`ChatAnthropic` / `ChatOpenAI` and `OpenAIEmbeddings`). Use `OPENAI_API_BASE` when traffic should go through an OpenAI-compatible proxy instead of the default vendor URL.

Implementation plan: [`docs/superpowers/plans/2026-03-21-mvp-0-bootstrap.md`](docs/superpowers/plans/2026-03-21-mvp-0-bootstrap.md).  
Full MVP chunk map: [`docs/superpowers/plans/2026-03-21-ai-portal-mvp-implementation.md`](docs/superpowers/plans/2026-03-21-ai-portal-mvp-implementation.md).

## Deploying to Render + Supabase

### 1. Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and create a new project.
2. In **Database → Extensions**, enable the **vector** extension (required for RAG).
3. Copy your connection string from **Settings → Database → Connection string → URI**.
   It looks like: `postgresql://postgres:[password]@[host]:5432/postgres`

### 2. Deploy to Render

1. Fork this repository.
2. In Render, click **New → Blueprint** and point it at your fork — Render will read `render.yaml` and create all three services automatically.
3. In the `ai-portal-api` service environment variables, set:
   - `DATABASE_URL` — paste the Supabase connection string
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` — your email provider (e.g. Resend, SendGrid, Gmail SMTP)
   - `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`
4. Update `CORS_ORIGINS` in `ai-portal-api` to your `ai-portal-app` URL (e.g. `https://ai-portal-app.onrender.com`).
5. Update `VITE_API_URL` in `ai-portal-app` to your `ai-portal-api` URL.
6. Update `VITE_APP_URL` in `ai-portal-landing` to your `ai-portal-app` URL.

### 3. First-time migration

Alembic migrations run automatically on every deploy via the `CMD` in `backend/Dockerfile`.

### Self-hosted mode

To deploy for a single organization:

1. Set `DEPLOYMENT_MODE=selfhosted` in the `ai-portal-api` environment.
2. On first boot, all API routes return `503 Setup Required`.
3. Navigate to `https://your-app-url/setup` to run the setup wizard.
4. Create your org and admin account — the instance is now live.

## API contract

The backend invokes models via **in-process LangChain**. A read-only **model catalog** is exposed at **`GET /api/model-catalog`** (seeded in DB; see REQ-META in [`docs/superpowers/specs/2026-03-22-model-platform-requirements.md`](docs/superpowers/specs/2026-03-22-model-platform-requirements.md)). Deeper entitlement / governance behavior is still specified there and in [`docs/superpowers/specs/2026-03-22-llm-access-model-governance-design.md`](docs/superpowers/specs/2026-03-22-llm-access-model-governance-design.md) — not all of it is enforced in API/UI yet.

The live API contract is defined by the running backend’s OpenAPI document. See [`contracts/README.md`](contracts/README.md) for **`GET /openapi.json`** as source of truth and how to save an optional local snapshot.
