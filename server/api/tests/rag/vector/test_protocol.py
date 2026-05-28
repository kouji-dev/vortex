"""Phase B: VectorStore protocol shape + DTO defaults."""

from __future__ import annotations

from ai_portal.rag.vector.protocol import (
    VectorFilter,
    VectorHit,
    VectorPoint,
    VectorStore,
)
from ai_portal.rag.vector.backends.memory import MemoryVectorStore


def test_vector_point_payload_defaults_to_empty_dict():
    p = VectorPoint(id="a", embedding=[0.1, 0.2])
    assert p.payload == {}


def test_vector_filter_is_empty_when_nothing_set():
    assert VectorFilter().is_empty()
    assert not VectorFilter(must={"k": "v"}).is_empty()
    assert not VectorFilter(must_not={"k": "v"}).is_empty()
    assert not VectorFilter(range={"t": {"gte": 1}}).is_empty()


def test_vector_hit_payload_defaults_to_empty_dict():
    h = VectorHit(id="a", score=0.9)
    assert h.payload == {}


def test_memory_backend_satisfies_protocol():
    store = MemoryVectorStore()
    assert isinstance(store, VectorStore)
    assert store.name == "memory"
