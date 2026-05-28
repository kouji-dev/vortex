"""Phase B: In-memory backend — upsert / query / filter / count / delete."""

from __future__ import annotations

import pytest

from ai_portal.rag.vector.backends.memory import MemoryVectorStore
from ai_portal.rag.vector.protocol import VectorFilter, VectorPoint


@pytest.mark.asyncio
async def test_upsert_then_query_returns_nearest_first():
    store = MemoryVectorStore()
    await store.ensure_namespace("kb-1", dim=3)
    await store.upsert(
        "kb-1",
        [
            VectorPoint(id="a", embedding=[1.0, 0.0, 0.0], payload={"kb_id": 1}),
            VectorPoint(id="b", embedding=[0.0, 1.0, 0.0], payload={"kb_id": 1}),
            VectorPoint(id="c", embedding=[0.0, 0.0, 1.0], payload={"kb_id": 1}),
        ],
    )
    hits = await store.query("kb-1", [1.0, 0.0, 0.0], top_k=2)
    assert hits[0].id == "a"
    assert hits[0].score > hits[1].score


@pytest.mark.asyncio
async def test_namespace_isolation():
    store = MemoryVectorStore()
    await store.upsert("kb-1", [VectorPoint(id="x", embedding=[1.0, 0.0])])
    await store.upsert("kb-2", [VectorPoint(id="y", embedding=[1.0, 0.0])])
    hits = await store.query("kb-1", [1.0, 0.0], top_k=10)
    assert {h.id for h in hits} == {"x"}


@pytest.mark.asyncio
async def test_filter_must_excludes_non_matching():
    store = MemoryVectorStore()
    await store.upsert(
        "kb-1",
        [
            VectorPoint(id="a", embedding=[1.0, 0.0], payload={"lang": "en"}),
            VectorPoint(id="b", embedding=[1.0, 0.0], payload={"lang": "fr"}),
        ],
    )
    hits = await store.query(
        "kb-1", [1.0, 0.0], top_k=10, flt=VectorFilter(must={"lang": "fr"})
    )
    assert {h.id for h in hits} == {"b"}


@pytest.mark.asyncio
async def test_filter_must_not_excludes_match():
    store = MemoryVectorStore()
    await store.upsert(
        "kb-1",
        [
            VectorPoint(id="a", embedding=[1.0, 0.0], payload={"src": "wiki"}),
            VectorPoint(id="b", embedding=[1.0, 0.0], payload={"src": "blog"}),
        ],
    )
    hits = await store.query(
        "kb-1", [1.0, 0.0], top_k=10, flt=VectorFilter(must_not={"src": "wiki"})
    )
    assert {h.id for h in hits} == {"b"}


@pytest.mark.asyncio
async def test_filter_range_filters_numeric():
    store = MemoryVectorStore()
    await store.upsert(
        "kb-1",
        [
            VectorPoint(id="a", embedding=[1.0, 0.0], payload={"ts": 1000}),
            VectorPoint(id="b", embedding=[1.0, 0.0], payload={"ts": 2000}),
            VectorPoint(id="c", embedding=[1.0, 0.0], payload={"ts": 3000}),
        ],
    )
    hits = await store.query(
        "kb-1", [1.0, 0.0], top_k=10, flt=VectorFilter(range={"ts": {"gte": 2000}})
    )
    assert {h.id for h in hits} == {"b", "c"}


@pytest.mark.asyncio
async def test_count_respects_filter():
    store = MemoryVectorStore()
    await store.upsert(
        "kb-1",
        [
            VectorPoint(id="a", embedding=[1.0], payload={"kind": "x"}),
            VectorPoint(id="b", embedding=[1.0], payload={"kind": "y"}),
        ],
    )
    assert await store.count("kb-1") == 2
    assert await store.count("kb-1", VectorFilter(must={"kind": "x"})) == 1


@pytest.mark.asyncio
async def test_delete_removes_ids():
    store = MemoryVectorStore()
    await store.upsert(
        "kb-1",
        [
            VectorPoint(id="a", embedding=[1.0]),
            VectorPoint(id="b", embedding=[1.0]),
        ],
    )
    await store.delete("kb-1", ["a"])
    assert await store.count("kb-1") == 1


@pytest.mark.asyncio
async def test_ensure_namespace_locks_dim():
    store = MemoryVectorStore()
    await store.ensure_namespace("kb-1", dim=3)
    with pytest.raises(ValueError):
        await store.ensure_namespace("kb-1", dim=4)
