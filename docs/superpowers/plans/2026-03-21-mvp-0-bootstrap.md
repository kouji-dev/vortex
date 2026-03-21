# MVP-0 — Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a runnable **API + web** foundation with **health checks in the browser and API**, **local dev infra**, a **shared API contract story**, **CI**, and **Azure-oriented configuration**—so later MVPs can ship vertical slices without reworking scaffolding.

**Architecture:** **FastAPI** backend (`backend/`) exposes `GET /health` and (optionally) `GET /openapi.json`; **TanStack Start** frontend (`frontend/`) — **Vite + React + TypeScript** with **`@tanstack/react-start`** — uses **TanStack Router** (file-based routes) for routing, **TanStack Query** for server state (e.g. the health check), and **Tailwind CSS** for styling—so later MVPs extend the same stack. The UI proves the app runs in the browser and can call the API (or show a clear error if the API is down). **Local Postgres and Redis** use **Docker Compose** with project name **`local-dev`** (Compose “namespace”), matching the pattern in **`kouji-factory/docker-compose.yml`** (same `name`, `POSTGRES_*` / redis layout). This repo uses **`pgvector/pgvector:pg17`** for Postgres so `vector` is available for RAG, and **distinct container names + host ports (5434 / 6380)** so ai-portal can run **alongside** kouji-factory (5433 / 6379) on one machine. The API may connect lazily in MVP-0 (health can stay DB-free until Task 3). **GitHub Actions** (or equivalent) runs **Ruff + pytest** on the backend and **`npm run build`** on the frontend. Configuration is **env-driven** with `.env.example` documenting variables suitable for local dev and **Azure** (Key Vault references described in comments, not secrets in repo).

**Tech Stack:** Python 3.12+, FastAPI, Uvicorn, Pydantic Settings, Ruff, Pytest, HTTPX, SQLAlchemy 2, Alembic, Psycopg (sync), Docker Compose, Node 20+, **TanStack Start** (Vite + **@tanstack/react-start**), React 19, TypeScript, **TanStack Router**, **TanStack Query**, **Tailwind CSS**, npm.

**Spec:** [`docs/superpowers/specs/README.md`](../specs/README.md) — **MVP-0** row; capabilities **F-01–F-04** (foundation).

---

## File map (greenfield)

| Path | Responsibility |
|------|----------------|
| `docker-compose.yml` | **`name: local-dev`**; Postgres + Redis (pattern from `kouji-factory/docker-compose.yml`; pgvector image; ports **127.0.0.1:5434** / **6380**) |
| `.env.example` | `DATABASE_URL` / `REDIS_URL` aligned with compose + kouji-factory `.env.example` shape; `CORS_ORIGINS`; Azure notes |
| `README.md` | Local `local-dev` stack, kouji-factory cross-reference, link to MVP-0 plan |
| `backend/pyproject.toml` | Dependencies, ruff, pytest |
| `backend/src/ai_portal/main.py` | FastAPI app, `/health`, CORS |
| `backend/src/ai_portal/config.py` | `pydantic-settings` |
| `backend/src/ai_portal/db/session.py` | Engine + session factory |
| `backend/alembic/` | Alembic config + first migration |
| `backend/tests/test_health.py` | Health contract test |
| `frontend/` | **TanStack Start** app; **TanStack Router** + **TanStack Query** + **Tailwind**; home route + API health query |
| `frontend/src/routes/` | File-based router tree (template demo routes OK; home proves API wiring) |
| `frontend/vite.config.ts` | **`tanstackStart()`** from `@tanstack/react-start/plugin/vite` + Tailwind v4 |
| `.github/workflows/ci.yml` | Lint, test, build |

---

### Task 1: Docker Compose (`local-dev`) + `.env.example` + root `README`

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1:** Add `docker-compose.yml` with top-level **`name: local-dev`** (Compose project / namespace). Copy **structure** from **`kouji-factory/docker-compose.yml`**: `db` + `redis`, `restart: unless-stopped`, `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD`, named volumes. Use image **`pgvector/pgvector:pg17`** for `db` (adds `vector` for RAG; kouji uses plain `postgres:17-alpine`). Use **`container_name`** values that **do not** collide with kouji (`local-dev-ai-portal-db`, `local-dev-ai-portal-redis`). Map **`127.0.0.1:5434:5432`** and **`127.0.0.1:6380:6379`** so ai-portal can run **in parallel** with kouji-factory (5433 / 6379).

- [ ] **Step 2:** Add `.env.example`: mirror **kouji-factory** `apps/api/.env.example` style (`DATABASE_URL`, `REDIS_URL` comments), but URLs must match **this** compose (**`postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal`**, **`redis://127.0.0.1:6380/0`**). Include `API_HOST`, `API_PORT`, `CORS_ORIGINS`, and Azure injection notes (no secrets in repo).

- [ ] **Step 3:** In `README.md`, document: copy `.env.example` → `.env`, `docker compose up -d`, `docker compose ps`, and point to kouji-factory’s compose for comparison.

- [ ] **Step 4:** If Task 1 files already exist from an earlier pass, **verify** they match this section; otherwise implement and commit.

- [ ] **Step 5:** Commit: `chore: local-dev compose (kouji-factory pattern) and env template`

---

### Task 2: Backend package + `GET /health` + pytest

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/ai_portal/__init__.py`
- Create: `backend/src/ai_portal/main.py`
- Create: `backend/src/ai_portal/config.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient
from ai_portal.main import app


def test_health_ok():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2:** From `backend/`, install editable + dev deps and run pytest; expect failure until app exists.

```bash
cd backend
pip install -e ".[dev]"
pytest tests/test_health.py -v
```

Expected: import or assertion failure.

- [ ] **Step 3: Minimal implementation**

`config.py`: `Settings` with `cors_origins: str = "http://localhost:5173"` (parse to list in app if comma-separated).

`main.py`: FastAPI app, `CORSMiddleware`, `GET /health` → `{"status": "ok"}`.

`pyproject.toml`: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx`; dev: `pytest`, `ruff`.

- [ ] **Step 4:** Run `pytest tests/test_health.py -v` — expect **PASS**.

- [ ] **Step 5:** Commit: `feat(api): fastapi health endpoint and package scaffold`

---

### Task 3: SQLAlchemy session + Alembic (minimal)

**Files:**
- Create: `backend/src/ai_portal/db/session.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_enable_extensions.py` (name as needed)
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/ai_portal/config.py`
- Modify: `README.md`

- [ ] **Step 1:** Add `sqlalchemy`, `alembic`, `psycopg[binary]` to `pyproject.toml`.

- [ ] **Step 2:** `session.py`: sync engine from `settings.database_url`, `SessionLocal` factory.

- [ ] **Step 3:** Wire Alembic `env.py` to load `DATABASE_URL` from settings; first migration runs `CREATE EXTENSION IF NOT EXISTS vector;` (and any minimal placeholder table optional—YAGNI: extension-only migration is OK for MVP-0).

- [ ] **Step 4:** Document `cd backend && alembic upgrade head` in `README.md` (requires Postgres up).

- [ ] **Step 5:** Commit: `feat(db): sqlalchemy session and alembic baseline`

---

### Task 4: Frontend scaffold — TanStack Start + Query + Tailwind + health check

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig*.json` (as generated by the template)
- Ensure: **`tanstackStart()`** in `vite.config.ts` (from `@tanstack/react-start/plugin/vite`) alongside `@tailwindcss/vite` and `@vitejs/plugin-react`
- Create: `frontend/src/routes/__root.tsx`, `frontend/src/routes/index.tsx`, plus router wiring per Start (`router.tsx`, generated `routeTree.gen.ts`, etc.)
- Create: `frontend/src/styles/app.css` (Tailwind v4: `@import "tailwindcss";` or equivalent per template)
- Create: `frontend/.env.example` with `VITE_API_URL`
- Modify: `README.md`

- [ ] **Step 1 — Bootstrap:** Scaffold from the official **TanStack Start** example **`start-basic-react-query`** (e.g. `npx gitpick TanStack/router/tree/main/examples/react/start-basic-react-query frontend` or the current TanStack CLI equivalent). Dev server should run on port **5173** (match root `CORS_ORIGINS`).

- [ ] **Step 2 — Tailwind:** Keep template **Tailwind v4** + `@tailwindcss/vite`; do not strip unless replacing with an equivalent global stylesheet.

- [ ] **Step 3 — Router + Query:** Use the template’s **`QueryClient` + `createRouter`** / file routes. Extra demo routes from the example are fine; **home (`/`)** must carry the MVP-0 health UI.

- [ ] **Step 4 — Health:** On the index route, use **`useQuery`** to `GET` `${VITE_API_URL}/health` (default e.g. `http://127.0.0.1:8000` if env unset). Render **success**, **JSON `status`**, or a **clear error** if the API is down.

- [ ] **Step 5:** Add `frontend/.env.example` with `VITE_API_URL=http://127.0.0.1:8000` (or `http://localhost:8000`; document copying to `frontend/.env` for local overrides).

- [ ] **Step 6:** Document in `README.md`: terminal A API, terminal B `cd frontend && npm run dev`, open browser at the Start dev URL/port.

- [ ] **Step 7:** Commit: `feat(web): tanstack start shell and api health query`

---

### Task 5: Shared contract story (OpenAPI)

**Files:**
- Modify: `README.md`
- Optional Create: `contracts/README.md`

- [ ] **Step 1:** Document that **`GET /openapi.json`** is the contract source of truth for MVP-0; future: OpenAPI → typed client (F-01).

- [ ] **Step 2:** Add a short `contracts/README.md` describing how to download/export OpenAPI after API is running (e.g. `curl http://localhost:8000/openapi.json -o contracts/openapi.json` when you choose to pin a snapshot).

- [ ] **Step 3:** Commit: `docs: openapi contract story for mvp-0`

---

### Task 6: CI (lint, test, build)

**Files:**
- Create: `.github/workflows/ci.yml`
- Optional: `backend/ruff.toml` or `[tool.ruff]` in `pyproject.toml`

- [ ] **Step 1:** Workflow on `push`/`pull_request`: job **backend** — checkout, setup Python 3.12, `pip install -e "./backend[dev]"`, `ruff check backend`, `pytest backend/tests -v`. Job **frontend** — setup Node 20, `npm ci` in `frontend`, `npm run build`.

- [ ] **Step 2:** If monorepo paths need adjustment, use `working-directory` in the workflow.

- [ ] **Step 3:** Commit: `ci: backend lint/test and frontend build`

---

## Definition of done (MVP-0)

- [ ] `docker compose up -d` brings up Postgres + Redis under Compose project **`local-dev`** (see `docker compose ls`).
- [ ] `GET /health` on the API returns **200** and `{"status":"ok"}`.
- [ ] Frontend dev server loads and **shows** API health (or clear error if API down).
- [ ] `alembic upgrade head` succeeds against local Postgres.
- [ ] CI is green on lint, pytest, and frontend build.

---

## After MVP-0

Proceed to **MVP-1** (identity + entitlements) per [`docs/superpowers/specs/README.md`](../specs/README.md); use a **new EPIC** under the same or a dedicated **scope** in the task manager.
