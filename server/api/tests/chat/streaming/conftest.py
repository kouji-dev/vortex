# server/api/tests/chat/streaming/conftest.py
from __future__ import annotations

import asyncio
import os
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Import all models so SQLAlchemy metadata is fully populated before async engine is created.
# Without this, FK resolution fails for tables like "users", "assistants" referenced by "threads".
import ai_portal.auth.model  # noqa: F401
import ai_portal.assistant.model  # noqa: F401
import ai_portal.chat.model  # noqa: F401

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.model import Thread, ThreadItem


# On Windows, psycopg async requires SelectorEventLoop (not ProactorEventLoop default).
# Override the event_loop_policy fixture so pytest-asyncio uses SelectorEventLoop.
if sys.platform == "win32":
    import selectors

    class _SelectorPolicy(asyncio.DefaultEventLoopPolicy):
        def new_event_loop(self) -> asyncio.AbstractEventLoop:
            return asyncio.SelectorEventLoop(selectors.SelectSelector())

    @pytest.fixture(scope="session")
    def event_loop_policy():  # type: ignore[misc]
        return _SelectorPolicy()


def _async_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # psycopg v3 handles async via postgresql+psycopg driver
    url = url.replace("+asyncpg", "+psycopg").replace("postgresql://", "postgresql+psycopg://")
    # Ensure it uses psycopg (not psycopg2)
    if "postgresql+psycopg2" in url:
        url = url.replace("postgresql+psycopg2", "postgresql+psycopg")
    if not url.startswith("postgresql"):
        return ""
    return url


@pytest.fixture(scope="module")
def async_engine():
    url = _async_url()
    if not url:
        pytest.fail("DATABASE_URL not set or Postgres unreachable")
    engine = create_async_engine(url, pool_pre_ping=True)
    yield engine
    # cleanup happens via event loop


@pytest_asyncio.fixture
async def async_db_session(async_engine):
    async with async_engine.begin() as conn:
        session = AsyncSession(bind=conn)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000cf2")
_USER_ID = 99902


@pytest_asyncio.fixture
async def org_fixture(async_db_session):
    existing = (await async_db_session.execute(
        text("SELECT id FROM orgs WHERE id = :id"), {"id": str(_ORG_ID)}
    )).first()
    if not existing:
        await async_db_session.execute(
            text("INSERT INTO orgs (id, slug, name) VALUES (:id, 'stream-test-org', 'Stream Test Org')"),
            {"id": str(_ORG_ID)},
        )
        await async_db_session.flush()

    class _Org:
        id = _ORG_ID

    return _Org()


@pytest_asyncio.fixture
async def user_fixture(async_db_session, org_fixture):
    existing = (await async_db_session.execute(
        text("SELECT id FROM users WHERE id = :id"), {"id": _USER_ID}
    )).first()
    if not existing:
        await async_db_session.execute(
            text("INSERT INTO users (id, email, uuid, org_id) VALUES (:uid, 'streamtest@example.com', gen_random_uuid(), :oid)"),
            {"uid": _USER_ID, "oid": str(org_fixture.id)},
        )
        await async_db_session.flush()

    class _User:
        id = _USER_ID
        org_id = _ORG_ID
        role = "member"

    return _User()


@pytest_asyncio.fixture
async def thread_fixture(async_db_session, org_fixture, user_fixture):
    t = Thread(org_id=org_fixture.id, user_id=user_fixture.id, title="stream-test", model="gpt-4")
    async_db_session.add(t)
    await async_db_session.flush()
    await async_db_session.refresh(t)
    return t


@pytest.fixture
def patched_fake_provider(monkeypatch):
    """Patch the orchestrator's _resolve_provider and turn_gate.evaluate for testing."""
    from ai_portal.catalog.providers.events import ProviderStreamEvent
    from ai_portal.chat.streaming import orchestrator
    from ai_portal.chat.streaming.turn_gate import GateResult

    script = [
        {"type": "text_delta", "text": "hi there"},
        {"type": "usage", "input_tokens": 5, "output_tokens": 3,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]

    class _FakeProvider:
        async def stream(self, *, messages=None, model=None, settings=None, tools=None, **kwargs):
            for e in script:
                yield ProviderStreamEvent.model_validate(e)

    monkeypatch.setattr(orchestrator, "_resolve_provider", lambda model: _FakeProvider())

    async def _pass_gate(**kwargs):
        return GateResult(effective_model="gpt-4", allowed_tools=[], allowed_capabilities=[])

    monkeypatch.setattr(orchestrator.turn_gate, "evaluate", _pass_gate)
