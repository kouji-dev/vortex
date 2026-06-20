"""Phase D2 — vector_qdrant recaller (optional dep)."""
from __future__ import annotations

import pytest

from ai_portal.memory.recallers import get, vector_qdrant


def test_sentinel_registered_regardless_of_dep() -> None:
    sent = get("vector_qdrant")
    assert sent.name == "vector_qdrant"
    assert hasattr(sent, "available")


def test_construct_when_dep_available() -> None:  # pragma: no cover - guarded
    if not vector_qdrant.QDRANT_AVAILABLE:
        pytest.fail("qdrant-client not installed")
    # Construct with a stub client; no network IO.
    class StubClient:
        async def search(self, **kw):
            return []

    inst = vector_qdrant.make_vector_qdrant(StubClient())
    assert inst.name == "vector_qdrant"
