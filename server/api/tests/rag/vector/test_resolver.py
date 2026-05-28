"""Phase B: per-KB backend resolver."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_portal.rag.vector import registry, resolve_for_kb
from ai_portal.rag.vector.backends.memory import MemoryVectorStore
from ai_portal.rag.vector.resolver import namespace_for_kb


def setup_function() -> None:
    registry._reset_for_tests()
    registry.register("memory", lambda cfg: MemoryVectorStore())


def test_resolve_for_kb_returns_backend_by_name():
    kb = SimpleNamespace(id=1, vector_backend="memory")
    store = resolve_for_kb(kb)
    assert isinstance(store, MemoryVectorStore)


def test_resolve_for_kb_defaults_to_pgvector_name_when_missing():
    # When the KB doesn't set vector_backend, resolver asks for ``pgvector``;
    # registry lookup must raise since pgvector isn't registered in this test.
    kb = SimpleNamespace(id=1, vector_backend=None)
    with pytest.raises(registry.UnknownVectorBackend):
        resolve_for_kb(kb)


def test_resolve_for_kb_unknown_backend_raises():
    kb = SimpleNamespace(id=1, vector_backend="bogus")
    with pytest.raises(registry.UnknownVectorBackend):
        resolve_for_kb(kb)


def test_namespace_for_kb_is_stable_and_id_scoped():
    kb_a = SimpleNamespace(id=7)
    kb_b = SimpleNamespace(id=42)
    assert namespace_for_kb(kb_a) == "kb-7"
    assert namespace_for_kb(kb_b) == "kb-42"


def test_namespace_for_kb_rejects_missing_id():
    with pytest.raises(ValueError):
        namespace_for_kb(SimpleNamespace(id=None))
