"""Redis cache backend — redis-py asyncio.

Values are JSON-encoded; TTL is enforced by Redis via ``SET ... EX <ttl>``.
A ``key_prefix`` lets callers namespace entries (e.g. per-org) on a shared
Redis instance.

The client is injected so callers can wire a connection pool / cluster / Sentinel
without this module depending on a particular factory.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis


class RedisCache:
    """Redis-backed prompt cache."""

    name = "redis"

    def __init__(
        self, client: Redis, key_prefix: str = "ai_portal:prompt_cache:"
    ) -> None:
        self._client = client
        self._prefix = key_prefix

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> dict[str, Any] | None:
        raw = await self._client.get(self._k(key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        if ttl <= 0:
            msg = f"ttl must be positive, got {ttl}"
            raise ValueError(msg)
        payload = json.dumps(value, separators=(",", ":"))
        await self._client.set(self._k(key), payload, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(self._k(key))
