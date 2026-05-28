"""Phase E2 — rag_backed store."""
from __future__ import annotations

import uuid as _uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_portal.memory.stores import get, rag_backed
from ai_portal.memory.stores.rag_backed import RagBackedStore


@pytest.mark.asyncio
async def test_upsert_with_rag_facade_calls_ingest(monkeypatch) -> None:
    s = RagBackedStore(session=None)  # type: ignore[arg-type]
    s.repo = SimpleNamespace(
        add=AsyncMock(side_effect=lambda m: m),
        get=AsyncMock(return_value=None),
        patch=AsyncMock(),
    )
    ingest = AsyncMock()
    monkeypatch.setattr(rag_backed, "_rag", lambda: SimpleNamespace(ingest_memory_chunk=ingest))
    mem = SimpleNamespace(
        id=None,
        org_id=_uuid.uuid4(),
        text="x",
        importance=0.5,
        confidence=0.5,
        tags_json=[],
        pinned=False,
        type=SimpleNamespace(value="fact"),
        scope_kind=SimpleNamespace(value="user"),
    )
    await s.upsert(mem)
    ingest.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_without_rag_falls_back(monkeypatch) -> None:
    s = RagBackedStore(session=None)  # type: ignore[arg-type]
    s.repo = SimpleNamespace(
        add=AsyncMock(side_effect=lambda m: m),
        get=AsyncMock(return_value=None),
        patch=AsyncMock(),
    )
    monkeypatch.setattr(rag_backed, "_rag", lambda: None)
    mem = SimpleNamespace(
        id=None,
        org_id=_uuid.uuid4(),
        text="x",
        importance=0.5,
        confidence=0.5,
        tags_json=[],
        pinned=False,
        type=SimpleNamespace(value="fact"),
        scope_kind=SimpleNamespace(value="user"),
    )
    out = await s.upsert(mem)
    assert out is mem
    s.repo.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_uses_repo_soft_delete_and_drop(monkeypatch) -> None:
    s = RagBackedStore(session=None)  # type: ignore[arg-type]
    s.repo = SimpleNamespace(soft_delete=AsyncMock())
    drop = AsyncMock()
    monkeypatch.setattr(rag_backed, "_rag", lambda: SimpleNamespace(drop_memory_chunk=drop))
    await s.delete("m1")
    s.repo.soft_delete.assert_awaited_once_with("m1")
    drop.assert_awaited_once_with(memory_id="m1")


def test_factory_registered() -> None:
    factory = get("rag_backed")
    assert callable(factory)
