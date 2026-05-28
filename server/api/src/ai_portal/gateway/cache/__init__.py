"""Prompt cache — pluggable key/value store with TTL.

Public surface:

- :class:`Cache` — backend protocol (`get`, `set`, `delete`).
- :class:`InMemoryCache` — dev / single-process default.
- :class:`RedisCache` — production backend (redis-py asyncio).
- :class:`PostgresCache` — no-Redis fallback, backed by ``prompt_cache_entries``.
- :func:`build_cache` — factory selecting backend by name from settings.

Stored values are opaque JSON-serialisable dicts (the gateway service hashes
the canonical :class:`LLMRequest` to derive the key and stores the
:class:`LLMResponse` dump). The protocol is intentionally minimal so the
service layer owns hashing, serialisation, and policy decisions.
"""

from __future__ import annotations

from ai_portal.gateway.cache.backends.inmemory import InMemoryCache
from ai_portal.gateway.cache.backends.postgres import PostgresCache
from ai_portal.gateway.cache.backends.redis import RedisCache
from ai_portal.gateway.cache.protocol import Cache
from ai_portal.gateway.cache.registry import (
    UnknownCacheBackend,
    build_cache,
    register_backend,
)

__all__ = [
    "Cache",
    "InMemoryCache",
    "PostgresCache",
    "RedisCache",
    "UnknownCacheBackend",
    "build_cache",
    "register_backend",
]
