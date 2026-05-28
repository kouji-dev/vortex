"""Phase B4 — policy protocol + registry."""
from __future__ import annotations

import pytest

from ai_portal.memory.extractors.protocol import ExtractScope, Turn
from ai_portal.memory.policies import registry
from ai_portal.memory.policies.protocol import MemoryPolicy
from ai_portal.memory.recallers.protocol import RecallScope


class _Fake:
    name = "fake_pol_unit"

    async def should_extract(self, turn: Turn, scope: ExtractScope) -> bool:
        return True

    async def should_recall(self, query: str, scope: RecallScope) -> bool:
        return True

    async def sensitive_category_match(self, text: str) -> list[str]:
        return []


def test_runtime_check_accepts_fake_policy() -> None:
    assert isinstance(_Fake(), MemoryPolicy)


def test_register_and_get() -> None:
    f = _Fake()
    registry.register(f)
    try:
        assert registry.get("fake_pol_unit") is f
        assert "fake_pol_unit" in registry.list_names()
    finally:
        registry._REG.pop("fake_pol_unit", None)


def test_get_unknown_raises() -> None:
    with pytest.raises(KeyError):
        registry.get("nope_xyz")
