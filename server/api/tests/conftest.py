from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text


def _postgres_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def postgres_available() -> bool:
    url = _postgres_url()
    if not url:
        return False
    try:
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OSError:
        return False
    return True


requires_postgres = pytest.mark.skipif(
    not postgres_available(),
    reason="DATABASE_URL not set or Postgres unreachable",
)


@pytest.fixture(scope="module")
def sync_engine():
    url = _postgres_url()
    if not url:
        pytest.skip("DATABASE_URL not set or Postgres unreachable")
    # Replace async driver with sync psycopg driver if needed
    sync_url = url.replace("+asyncpg", "+psycopg").replace(
        "postgresql+psycopg2", "postgresql+psycopg"
    )
    if not sync_url.startswith("postgresql"):
        pytest.skip("DATABASE_URL not set or Postgres unreachable")
    eng = create_engine(sync_url, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OSError:
        pytest.skip("Postgres unreachable")
    yield eng
    eng.dispose()
