# AI Portal

Self-hosted AI portal (spec: [`docs/superpowers/specs/README.md`](docs/superpowers/specs/README.md)).

## Local dev — Postgres & Redis (`local-dev`)

Infrastructure follows the same **Docker Compose project name** and layout as **kouji-factory** (`name: local-dev`, postgres + redis, named volumes). See `docker-compose.yml` and compare with `../kouji-factory/docker-compose.yml`.

- **This repo** uses host ports **5434** (Postgres) and **6380** (Redis) so you can run **ai-portal** next to **kouji-factory** (which uses **5433** / **6379**).
- Postgres image is **`pgvector/pgvector:pg17`** so the `vector` extension is available for RAG.

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

Connection strings are in `.env.example` (`DATABASE_URL`, `REDIS_URL`).

## API + web (MVP-0)

- **Backend:** from `backend/`, run Uvicorn on port **8000** (see `backend/README.md`). `CORS_ORIGINS` in `.env` should include **`http://localhost:5173`** (TanStack Start dev server).
- **Frontend:** **`frontend/`** is **TanStack Start** (Vite + `@tanstack/react-start`, TanStack Router file routes, TanStack Query, Tailwind v4). Copy `frontend/.env.example` → `frontend/.env` if you need to override **`VITE_API_URL`** (defaults to `http://127.0.0.1:8000` in code).

```bash
cd frontend
npm install
npm run dev
```

Copy `frontend/.env.example` → `frontend/.env` and set **`VITE_DEV_TOKEN=devtoken`** so catalog/chat routes can call the API.

### Full stack in Docker (optional)

With **Postgres + Redis** already up (`docker compose up -d`), build and run API, Celery worker, and web:

```bash
docker compose --profile full build
docker compose --profile full run --rm api alembic upgrade head
docker compose --profile full up -d api worker web
```

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000) — web UI: [http://127.0.0.1:3000](http://127.0.0.1:3000)  
- Set **`OPENAI_API_KEY`** in `.env` (or the shell) before `up` so chat/embeddings work.

Optional LiteLLM proxy: `docker compose --profile litellm up -d litellm` (see comments in `docker-compose.yml`).

Implementation plan: [`docs/superpowers/plans/2026-03-21-mvp-0-bootstrap.md`](docs/superpowers/plans/2026-03-21-mvp-0-bootstrap.md).  
Full MVP chunk map: [`docs/superpowers/plans/2026-03-21-ai-portal-mvp-implementation.md`](docs/superpowers/plans/2026-03-21-ai-portal-mvp-implementation.md).

## API contract

The **MVP-0** API contract is defined by the running backend’s OpenAPI document. See [`contracts/README.md`](contracts/README.md) for **`GET /openapi.json`** as source of truth and how to save an optional local snapshot.
