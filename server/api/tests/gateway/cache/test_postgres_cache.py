"""PostgresCache — prompt_cache_entries table.

Requires a live Postgres + the ``prompt_cache_entries`` migration applied.
Skipped when DATABASE_URL is unset or unreachable.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def event_loop_policy():
    # psycopg async refuses ProactorEventLoop on Windows.
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


def _async_pg_url() -> str | None:
    url = os.environ.get("DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        return None
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@pytest.fixture
async def session_factory():
    url = _async_pg_url()
    if not url:
        pytest.skip("DATABASE_URL not set or non-postgres")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            # confirm migration was applied
            res = await conn.execute(
                text("SELECT to_regclass('public.prompt_cache_entries') IS NOT NULL")
            )
            if not res.scalar():
                pytest.skip(
                    "prompt_cache_entries table not present (migration not applied)"
                )
    except OSError:
        await engine.dispose()
        pytest.skip("Postgres unreachable")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


async def _cleanup(session_factory, org_id) -> None:
    async with session_factory() as s:
        await s.execute(text("SET LOCAL app.bypass_rls = 'on'"))
        await s.execute(
            text("DELETE FROM prompt_cache_entries WHERE org_id = :o"),
            {"o": str(org_id)},
        )
        await s.commit()


async def test_protocol_compliance(session_factory, org_id) -> None:
    from ai_portal.gateway.cache import Cache, PostgresCache

    cache = PostgresCache(session_factory=session_factory, org_id=org_id)
    assert isinstance(cache, Cache)
    assert cache.name == "postgres"


async def test_set_get_roundtrip(session_factory, org_id) -> None:
    from ai_portal.gateway.cache import PostgresCache

    cache = PostgresCache(session_factory=session_factory, org_id=org_id)
    try:
        value = {"id": "p1", "content": [{"type": "text", "text": "hi"}]}
        await cache.set("k1", value, ttl=60)
        assert await cache.get("k1") == value
    finally:
        await _cleanup(session_factory, org_id)


async def test_get_missing_returns_none(session_factory, org_id) -> None:
    from ai_portal.gateway.cache import PostgresCache

    cache = PostgresCache(session_factory=session_factory, org_id=org_id)
    assert await cache.get("missing") is None


async def test_ttl_expiry_deletes_entry(session_factory, org_id) -> None:
    from ai_portal.gateway.cache import PostgresCache

    cache = PostgresCache(session_factory=session_factory, org_id=org_id)
    try:
        # Insert with a row whose expires_at is in the past
        await cache.set("k", {"v": 1}, ttl=1)
        async with session_factory() as s:
            await s.execute(text("SET LOCAL app.bypass_rls = 'on'"))
            await s.execute(
                text(
                    "UPDATE prompt_cache_entries "
                    "SET expires_at = now() - interval '1 minute' "
                    "WHERE org_id = :o AND cache_key = 'k'"
                ),
                {"o": str(org_id)},
            )
            await s.commit()
        # get must observe expiry and delete lazily
        assert await cache.get("k") is None
        # confirm row physically removed (lazy eviction)
        async with session_factory() as s:
            await s.execute(text("SET LOCAL app.bypass_rls = 'on'"))
            row = await s.execute(
                text(
                    "SELECT count(*) FROM prompt_cache_entries "
                    "WHERE org_id = :o AND cache_key = 'k'"
                ),
                {"o": str(org_id)},
            )
            assert row.scalar() == 0
    finally:
        await _cleanup(session_factory, org_id)


async def test_delete_idempotent(session_factory, org_id) -> None:
    from ai_portal.gateway.cache import PostgresCache

    cache = PostgresCache(session_factory=session_factory, org_id=org_id)
    try:
        await cache.delete("never")  # missing — no raise
        await cache.set("k", {"v": 1}, ttl=10)
        await cache.delete("k")
        assert await cache.get("k") is None
        await cache.delete("k")
    finally:
        await _cleanup(session_factory, org_id)


async def test_overwrite_replaces_value_and_ttl(session_factory, org_id) -> None:
    from ai_portal.gateway.cache import PostgresCache

    cache = PostgresCache(session_factory=session_factory, org_id=org_id)
    try:
        await cache.set("k", {"v": 1}, ttl=5)
        await cache.set("k", {"v": 2}, ttl=99)
        assert await cache.get("k") == {"v": 2}
    finally:
        await _cleanup(session_factory, org_id)


async def test_org_isolation(session_factory, org_id) -> None:
    from ai_portal.gateway.cache import PostgresCache

    other_org = uuid.uuid4()
    a = PostgresCache(session_factory=session_factory, org_id=org_id)
    b = PostgresCache(session_factory=session_factory, org_id=other_org)
    try:
        await a.set("k", {"v": "a"}, ttl=30)
        await b.set("k", {"v": "b"}, ttl=30)
        assert await a.get("k") == {"v": "a"}
        assert await b.get("k") == {"v": "b"}
    finally:
        await _cleanup(session_factory, org_id)
        await _cleanup(session_factory, other_org)


async def test_set_rejects_non_positive_ttl(session_factory, org_id) -> None:
    from ai_portal.gateway.cache import PostgresCache

    cache = PostgresCache(session_factory=session_factory, org_id=org_id)
    with pytest.raises(ValueError):
        await cache.set("k", {"v": 1}, ttl=0)
