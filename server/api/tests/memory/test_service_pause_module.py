"""Phase G/K — pause + module-flag short-circuit (mocked repo + policies)."""
from __future__ import annotations

import pytest

from ai_portal.memory.extractors.protocol import ExtractOpts, ExtractScope, Turn
from ai_portal.memory.service import MemoryService


class _FakeSession:
    """Minimal session stub used only via service hooks that we monkeypatch."""

    def add(self, *_a, **_k):
        pass

    async def flush(self):
        pass

    async def execute(self, *_a, **_k):
        class _R:
            def scalar_one_or_none(self):
                return None

            def scalars(self):
                class _S:
                    def all(self):
                        return []

                return _S()

            @property
            def rowcount(self):
                return 0

            def all(self):
                return []

        return _R()


@pytest.mark.asyncio
async def test_extract_skips_when_module_disabled(monkeypatch) -> None:
    async def fake_disabled(_org):
        return False

    monkeypatch.setattr("ai_portal.memory.service._is_module_enabled", fake_disabled)
    svc = MemoryService(_FakeSession())  # type: ignore[arg-type]
    scope = ExtractScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        scope_kind="user",
        scope_id="1",
    )
    res = await svc.extract(
        [Turn(role="user", content="hi", turn_id="t")], scope, ExtractOpts()
    )
    assert res.skipped_module_disabled is True
    assert res.created == [] and res.updated == []


@pytest.mark.asyncio
async def test_extract_skips_when_paused(monkeypatch) -> None:
    async def fake_enabled(_org):
        return True

    async def fake_paused(self, *_a, **_k):
        return True

    monkeypatch.setattr("ai_portal.memory.service._is_module_enabled", fake_enabled)
    monkeypatch.setattr(MemoryService, "_is_paused", fake_paused)
    svc = MemoryService(_FakeSession())  # type: ignore[arg-type]
    scope = ExtractScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        scope_kind="user",
        scope_id="1",
    )
    res = await svc.extract(
        [Turn(role="user", content="hi", turn_id="t")], scope, ExtractOpts()
    )
    assert res.skipped_paused is True
