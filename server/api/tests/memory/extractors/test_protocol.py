"""Phase B1 — extractor protocol + registry."""
from __future__ import annotations

import pytest

from ai_portal.memory.extractors.protocol import (
    Candidate,
    ExtractOpts,
    ExtractScope,
    Extractor,
    Turn,
)
from ai_portal.memory.extractors import registry


class _Fake:
    name = "fake_unit"

    async def extract(
        self,
        turns: list[Turn],
        scope: ExtractScope,
        opts: ExtractOpts,
    ) -> list[Candidate]:
        return [Candidate(type="fact", text="x", confidence=1.0)]


def test_runtime_check_accepts_fake_extractor() -> None:
    assert isinstance(_Fake(), Extractor)


def test_register_and_get() -> None:
    f = _Fake()
    registry.register(f)
    try:
        assert registry.get("fake_unit") is f
        assert "fake_unit" in registry.list_names()
    finally:
        # leave the global registry unchanged for other tests
        registry._REG.pop("fake_unit", None)


def test_get_unknown_raises() -> None:
    with pytest.raises(KeyError):
        registry.get("nope_does_not_exist_xyz")
