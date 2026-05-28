"""RedisCache — redis-py asyncio.

Use fakeredis if available; otherwise skip. We do not require a live Redis.
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.asyncio

fakeredis = pytest.importorskip("fakeredis")

from ai_portal.gateway.cache import Cache, RedisCache  # noqa: E402


def _make_client():
    # fakeredis ships an asyncio client compatible with redis.asyncio.Redis
    return fakeredis.aioredis.FakeRedis(decode_responses=False)


async def test_protocol_compliance() -> None:
    cache = RedisCache(client=_make_client())
    assert isinstance(cache, Cache)
    assert cache.name == "redis"


async def test_set_get_roundtrip() -> None:
    cache = RedisCache(client=_make_client())
    value = {"id": "r1", "content": [{"type": "text", "text": "hello"}]}
    await cache.set("k", value, ttl=60)
    got = await cache.get("k")
    assert got == value


async def test_get_missing_returns_none() -> None:
    cache = RedisCache(client=_make_client())
    assert await cache.get("nope") is None


async def test_ttl_expiry_deletes_entry() -> None:
    client = _make_client()
    cache = RedisCache(client=client)
    await cache.set("k", {"v": 1}, ttl=1)
    # fakeredis time-travel: advance internal clock
    await client.expire("k", 0)  # force immediate expiry
    # poll a tiny bit; expiry should be observable
    for _ in range(20):
        if await cache.get("k") is None:
            break
        await asyncio.sleep(0.01)
    assert await cache.get("k") is None


async def test_delete_idempotent() -> None:
    cache = RedisCache(client=_make_client())
    await cache.delete("never")  # no raise
    await cache.set("k", {"v": 1}, ttl=10)
    await cache.delete("k")
    assert await cache.get("k") is None
    await cache.delete("k")


async def test_set_rejects_non_positive_ttl() -> None:
    cache = RedisCache(client=_make_client())
    with pytest.raises(ValueError):
        await cache.set("k", {"v": 1}, ttl=0)


async def test_key_prefix_namespacing() -> None:
    client = _make_client()
    a = RedisCache(client=client, key_prefix="org_a:")
    b = RedisCache(client=client, key_prefix="org_b:")
    await a.set("k", {"v": "a"}, ttl=10)
    await b.set("k", {"v": "b"}, ttl=10)
    assert await a.get("k") == {"v": "a"}
    assert await b.get("k") == {"v": "b"}
