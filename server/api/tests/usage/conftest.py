# server/api/tests/usage/conftest.py
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Import all models so SQLAlchemy metadata is fully populated.
import ai_portal.auth.model  # noqa: F401
import ai_portal.assistant.model  # noqa: F401
import ai_portal.chat.model  # noqa: F401

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.model import Thread, ThreadItem


# On Windows, psycopg async requires SelectorEventLoop.
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
    url = url.replace("+asyncpg", "+psycopg").replace("postgresql://", "postgresql+psycopg://")
    if "postgresql+psycopg2" in url:
        url = url.replace("postgresql+psycopg2", "postgresql+psycopg")
    if not url.startswith("postgresql"):
        return ""
    return url


@pytest.fixture(scope="module")
def async_engine():
    url = _async_url()
    if not url:
        pytest.fail("DATABASE_URL not set")
    engine = create_async_engine(url, pool_pre_ping=True)
    yield engine


@pytest_asyncio.fixture
async def async_db_session(async_engine):
    async with async_engine.begin() as conn:
        session = AsyncSession(conn)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000cf3")
_USER_ID = 99903


@pytest_asyncio.fixture
async def thread_items_fixture(async_db_session):
    await async_db_session.execute(text(
        "INSERT INTO orgs (id, slug, name) VALUES (:id, 'cons-test', 'Cons Test') ON CONFLICT DO NOTHING"
    ), {"id": str(_ORG_ID)})
    await async_db_session.execute(text(
        "INSERT INTO users (id, email, uuid, org_id) VALUES (:uid, 'cons@test.com', gen_random_uuid(), :oid) ON CONFLICT DO NOTHING"
    ), {"uid": _USER_ID, "oid": str(_ORG_ID)})

    thread = Thread(org_id=_ORG_ID, user_id=_USER_ID, title="cons-thread", model="gpt-4")
    async_db_session.add(thread)
    await async_db_session.flush()
    await async_db_session.refresh(thread)

    turn = uuid.uuid4()
    items = [
        ThreadItem(
            thread_id=thread.id, org_id=_ORG_ID, turn_id=turn,
            kind=ItemKind.llm_call, role=ItemRole.assistant, status=ItemStatus.done,
            model="gpt-4", cost_usd=Decimal("0.005"), cost_estimated=False,
            data={
                "input_tokens": 100, "output_tokens": 50,
                "cached_input_tokens": 0, "cache_creation_input_tokens": 0,
                "reasoning_tokens": 0, "iteration_index": 0,
            },
        ),
        ThreadItem(
            thread_id=thread.id, org_id=_ORG_ID, turn_id=turn,
            kind=ItemKind.tool_call, role=ItemRole.assistant, status=ItemStatus.done,
            provider="tavily", cost_usd=Decimal("0.001"), cost_estimated=True,
            data={"tool_name": "web_search", "params": {}},
        ),
        ThreadItem(
            thread_id=thread.id, org_id=_ORG_ID, turn_id=turn,
            kind=ItemKind.assistant_text, role=ItemRole.assistant, status=ItemStatus.done,
            data={"text": "hello"},
        ),
    ]
    for item in items:
        async_db_session.add(item)
    await async_db_session.flush()

    return thread
