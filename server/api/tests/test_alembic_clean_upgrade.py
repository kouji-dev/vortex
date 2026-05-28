"""Verify the full alembic migration chain applies cleanly to an empty DB.

This test is opt-in: skipped unless ``SCRATCH_DATABASE_URL`` is set. The URL
must point at a Postgres server where the test can create + drop a scratch
database. The test never touches the real dev/E2E databases.

Run locally (against the e2e container on port 5435):

    SCRATCH_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_scratch \\
        pytest server/api/tests/test_alembic_clean_upgrade.py -v
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url


_SCRATCH_URL_ENV = "SCRATCH_DATABASE_URL"


def _scratch_url() -> str | None:
    return os.environ.get(_SCRATCH_URL_ENV)


def _postgres_root_url(scratch_url: str) -> str:
    """Return a URL pointing at the `postgres` DB on the same server.

    We need a separate connection to a known DB so we can DROP + CREATE the
    scratch DB.
    """
    url = make_url(scratch_url)
    # Replace the dbname with `postgres` (the default maintenance DB).
    # Use render_as_string(hide_password=False) — bare `str(url)` masks the pwd.
    return url.set(database="postgres").render_as_string(hide_password=False)


pytestmark = pytest.mark.skipif(
    not _scratch_url(),
    reason=f"{_SCRATCH_URL_ENV} not set — skipping clean-upgrade test",
)


def test_alembic_upgrade_head_from_empty_database() -> None:
    """`alembic upgrade head` succeeds against a freshly-created empty DB."""
    scratch_url = _scratch_url()
    assert scratch_url is not None  # for type-checkers; pytestmark guarantees

    parsed = make_url(scratch_url)
    # Use a unique DB name per run so concurrent runs don't trip over each other.
    db_name = f"ai_portal_alembic_test_{uuid.uuid4().hex[:12]}"
    test_url = parsed.set(database=db_name).render_as_string(hide_password=False)
    root_url = _postgres_root_url(scratch_url)

    root = create_engine(root_url, isolation_level="AUTOCOMMIT")
    try:
        with root.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))

        # Run alembic upgrade head against the fresh DB.
        # Import locally so module collection works even without alembic.
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        api_root = Path(__file__).resolve().parent.parent
        cfg = Config(str(api_root / "alembic.ini"))
        # Make sure alembic's env.py picks up the scratch URL.
        os.environ["DATABASE_URL"] = test_url
        try:
            command.upgrade(cfg, "head")

            # Verify the post-state matches the script's head revision exactly.
            script = ScriptDirectory.from_config(cfg)
            heads = script.get_heads()
            assert len(heads) == 1, f"expected single head, got {heads!r}"
            expected_head = heads[0]

            eng = create_engine(test_url)
            with eng.connect() as conn:
                row = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).first()
                assert row is not None, "alembic_version table empty after upgrade"
                assert row[0] == expected_head, (
                    f"alembic_version mismatch: db={row[0]!r} expected={expected_head!r}"
                )
            eng.dispose()
        finally:
            # Restore env to scratch URL value (not the per-test DB).
            os.environ["DATABASE_URL"] = scratch_url
    finally:
        # Cleanup: drop the test DB regardless of outcome.
        with root.connect() as conn:
            # Disconnect any leftover sessions before drop.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        root.dispose()
