"""In-memory cache backend — dict + TTL + asyncio lock.

Suitable for dev and single-process deployments. Not shared across workers.
TTL is enforced lazily on :meth:`get` and eagerly on :meth:`set` overwrites.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _Entry:
    value: dict[str, Any]
    expires_at: float


class InMemoryCache:
    """Dict-backed cache with TTL and an asyncio lock for safe mutation."""

    name = "inmemory"

    def __init__(self, time_source: Callable[[], float] | None = None) -> None:
        self._store: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()
        self._clock: Callable[[], float] = time_source or time.monotonic

    async def get(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                # lazy eviction
                self._store.pop(key, None)
                return None
            return dict(entry.value)

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        if ttl <= 0:
            msg = f"ttl must be positive, got {ttl}"
            raise ValueError(msg)
        async with self._lock:
            self._store[key] = _Entry(
                value=dict(value),
                expires_at=self._clock() + ttl,
            )

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)
