"""InMemoryCache — dict + TTL + asyncio lock.

Set/get roundtrip; TTL expiry deletes; delete is idempotent; concurrent
set/delete is consistent.
"""

from __future__ import annotations

import asyncio

import pytest

from ai_portal.gateway.cache import Cache, InMemoryCache

pytestmark = pytest.mark.asyncio


async def test_protocol_compliance() -> None:
    cache = InMemoryCache()
    assert isinstance(cache, Cache)
    assert cache.name == "inmemory"


async def test_set_get_roundtrip() -> None:
    cache = InMemoryCache()
    value = {"id": "resp_1", "content": [{"type": "text", "text": "hi"}]}
    await cache.set("k", value, ttl=60)
    got = await cache.get("k")
    assert got == value


async def test_get_missing_returns_none() -> None:
    cache = InMemoryCache()
    assert await cache.get("missing") is None


async def test_ttl_expiry_deletes_entry() -> None:
    cache = InMemoryCache(time_source=_FakeClock(start=0.0))
    await cache.set("k", {"v": 1}, ttl=1)
    # advance past TTL
    cache._clock.advance(2.0)  # type: ignore[attr-defined]
    assert await cache.get("k") is None
    # internal eviction: subsequent set must also work
    await cache.set("k", {"v": 2}, ttl=1)
    assert await cache.get("k") == {"v": 2}


async def test_delete_idempotent() -> None:
    cache = InMemoryCache()
    await cache.delete("never-existed")  # no raise
    await cache.set("k", {"v": 1}, ttl=10)
    await cache.delete("k")
    assert await cache.get("k") is None
    await cache.delete("k")  # second delete also fine


async def test_overwrite_resets_ttl() -> None:
    clock = _FakeClock(start=0.0)
    cache = InMemoryCache(time_source=clock)
    await cache.set("k", {"v": 1}, ttl=5)
    clock.advance(4.0)
    await cache.set("k", {"v": 2}, ttl=5)  # refresh
    clock.advance(3.0)  # 7s since first set, 3s since second
    assert await cache.get("k") == {"v": 2}


async def test_concurrent_sets_consistent() -> None:
    cache = InMemoryCache()

    async def writer(i: int) -> None:
        for _ in range(50):
            await cache.set(f"k{i}", {"i": i}, ttl=10)

    await asyncio.gather(*(writer(i) for i in range(8)))
    for i in range(8):
        assert await cache.get(f"k{i}") == {"i": i}


async def test_set_rejects_non_positive_ttl() -> None:
    cache = InMemoryCache()
    with pytest.raises(ValueError):
        await cache.set("k", {"v": 1}, ttl=0)
    with pytest.raises(ValueError):
        await cache.set("k", {"v": 1}, ttl=-3)


class _FakeClock:
    def __init__(self, start: float) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt
