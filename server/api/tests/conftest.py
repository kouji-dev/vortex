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
