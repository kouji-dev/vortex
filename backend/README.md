# AI Portal API

## Run (dev)

From repo root, with Postgres/Redis up (`docker compose up -d`):

```bash
cd backend
pip install -e ".[dev]"
uvicorn ai_portal.main:app --reload --host 0.0.0.0 --port 8000
```

Env: copy repo root `.env.example` to `.env` or set `DATABASE_URL` / `REDIS_URL`.

## Tests

```bash
cd backend
pytest tests -v
```

## Migrations

```bash
cd backend
alembic upgrade head
```
