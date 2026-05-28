"""Phase B3 — store protocol + registry."""
from __future__ import annotations

import pytest

from ai_portal.memory.stores import registry
from ai_portal.memory.stores.protocol import MemoryStore


class _FakeStore:
    name = "fake_store_unit"

    async def upsert(self, memory):
        return memory

    async def delete(self, memory_id: str) -> None:
        return None

    async def list_for_actor(self, *, org_id, actor_user_id, team_ids=None, **kw):
        return []

    async def search(self, *, org_id, embedding, limit=20, **kw):
        return []


def test_runtime_check_accepts_fake_store() -> None:
    assert isinstance(_FakeStore(), MemoryStore)


def test_register_factory_and_get() -> None:
    def factory(session=None):
        return _FakeStore()

    registry.register("fake_store_unit", factory)
    try:
        f = registry.get("fake_store_unit")
        store = f()
        assert store.name == "fake_store_unit"
        assert "fake_store_unit" in registry.list_names()
    finally:
        registry._REG.pop("fake_store_unit", None)


def test_get_unknown_raises() -> None:
    with pytest.raises(KeyError):
        registry.get("nope_xyz")
