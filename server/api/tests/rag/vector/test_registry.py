"""Phase B: VectorStore registry rejects duplicates + resolves by name."""

from __future__ import annotations

import pytest

from ai_portal.rag.vector import registry
from ai_portal.rag.vector.backends.memory import MemoryVectorStore


def setup_function() -> None:
    registry._reset_for_tests()


def test_register_then_get_returns_built_store():
    registry.register("memory", lambda cfg: MemoryVectorStore())
    store = registry.get("memory")
    assert isinstance(store, MemoryVectorStore)


def test_duplicate_registration_raises():
    registry.register("memory", lambda cfg: MemoryVectorStore())
    with pytest.raises(registry.DuplicateBackend):
        registry.register("memory", lambda cfg: MemoryVectorStore())


def test_unknown_backend_raises():
    with pytest.raises(registry.UnknownVectorBackend):
        registry.get("missing")


def test_names_lists_registered_backends_sorted():
    registry.register("memory", lambda cfg: MemoryVectorStore())
    registry.register("alpha", lambda cfg: MemoryVectorStore())
    assert registry.names() == ("alpha", "memory")
