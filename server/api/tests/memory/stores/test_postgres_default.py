"""Phase E1 — postgres_default store (mocked MemoryRepo)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_portal.memory.stores import get, postgres_default
from ai_portal.memory.stores.postgres_default import PostgresDefaultStore


@pytest.mark.asyncio
async def test_upsert_new_calls_add() -> None:
    s = PostgresDefaultStore(session=None)  # type: ignore[arg-type]
    s.repo = SimpleNamespace(
        add=AsyncMock(side_effect=lambda m: m),
        get=AsyncMock(return_value=None),
        patch=AsyncMock(),
    )
    fake_mem = SimpleNamespace(id=None, text="x")
    out = await s.upsert(fake_mem)
    s.repo.add.assert_awaited_once()
    assert out is fake_mem


@pytest.mark.asyncio
async def test_upsert_existing_calls_patch() -> None:
    s = PostgresDefaultStore(session=None)  # type: ignore[arg-type]
    existing = SimpleNamespace(id="m1")

    async def _get(mid):
        return existing

    s.repo = SimpleNamespace(
        add=AsyncMock(),
        get=AsyncMock(side_effect=_get),
        patch=AsyncMock(),
    )
    new_mem = SimpleNamespace(
        id="m1", text="updated", importance=0.7, confidence=0.8,
        tags_json=["a"], pinned=True,
    )
    await s.upsert(new_mem)
    s.repo.patch.assert_awaited_once()
    s.repo.add.assert_not_called()


@pytest.mark.asyncio
async def test_delete_soft_deletes() -> None:
    s = PostgresDefaultStore(session=None)  # type: ignore[arg-type]
    s.repo = SimpleNamespace(soft_delete=AsyncMock())
    await s.delete("m1")
    s.repo.soft_delete.assert_awaited_once_with("m1")


@pytest.mark.asyncio
async def test_search_delegates_to_vector_search() -> None:
    s = PostgresDefaultStore(session=None)  # type: ignore[arg-type]
    s.repo = SimpleNamespace(vector_search=AsyncMock(return_value=[]))
    await s.search(
        org_id="00000000-0000-0000-0000-000000000001",
        embedding=[0.0] * 1536,
        limit=5,
    )
    s.repo.vector_search.assert_awaited_once()


def test_factory_registered() -> None:
    factory = get("postgres_default")
    assert callable(factory)
