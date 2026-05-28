"""Phase B: ensure_registered wires all bundled backends."""

from __future__ import annotations

from ai_portal.rag.vector import registry
from ai_portal.rag.vector.backends import ensure_registered


def setup_function() -> None:
    registry._reset_for_tests()


def test_ensure_registered_includes_default_set():
    ensure_registered()
    names = set(registry.names())
    assert {"memory", "pgvector", "qdrant", "pinecone", "weaviate"} <= names


def test_ensure_registered_is_idempotent():
    ensure_registered()
    ensure_registered()  # second call must not raise DuplicateBackend
    names = set(registry.names())
    assert "memory" in names


def test_memory_backend_factory_builds_a_store():
    ensure_registered()
    store = registry.get("memory")
    assert store.name == "memory"
