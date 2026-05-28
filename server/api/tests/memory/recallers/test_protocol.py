"""Phase B2 — recaller protocol + registry."""
from __future__ import annotations

import pytest

from ai_portal.memory.recallers.protocol import (
    RecallOpts,
    RecallScope,
    Recalled,
    Recaller,
)
from ai_portal.memory.recallers import registry


class _Fake:
    name = "fake_recall_unit"

    async def recall(self, query: str, scope: RecallScope, opts: RecallOpts) -> list[Recalled]:
        return [Recalled(memory_id="m1", text="x", score=0.5, explain={})]


def test_runtime_check_accepts_fake() -> None:
    assert isinstance(_Fake(), Recaller)


def test_register_and_get() -> None:
    f = _Fake()
    registry.register(f)
    try:
        assert registry.get("fake_recall_unit") is f
        assert "fake_recall_unit" in registry.list_names()
    finally:
        registry._REG.pop("fake_recall_unit", None)


def test_get_unknown_raises() -> None:
    with pytest.raises(KeyError):
        registry.get("nope_xyz")
