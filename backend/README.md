# AI Portal API

## Run (dev)

From repo root, with Postgres/Redis up (`docker compose up -d`):

```bash
cd backend
pip install -e ".[dev]"
uvicorn ai_portal.main:app --reload --host 0.0.0.0 --port 8000
```

Env: copy repo root `.env.example` to `.env`. Important keys: `DATABASE_URL`, `REDIS_URL`, `DEV_BEARER_TOKEN`, `DEV_SEED_USER_EMAIL`, `OPENAI_API_KEY` (for chat + embeddings), `UPLOAD_DIR`.

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

Order: `001` (vector extension) → `002_core_catalog` → `003_chat` → `004_rag`.

```bash
cd backend
alembic upgrade head
```
