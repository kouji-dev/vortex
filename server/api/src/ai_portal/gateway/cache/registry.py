"""Cache backend registry — name → factory; settings-driven selection.

Bundled backends auto-register on import. Callers select a backend by name:

>>> cache = build_cache("inmemory")
>>> cache = build_cache("redis", client=my_redis)
>>> cache = build_cache("postgres", session_factory=sf, org_id=org)

Custom backends register via :func:`register_backend` and become buildable by
the same name. Unknown names raise :class:`UnknownCacheBackend`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_portal.gateway.cache.backends.inmemory import InMemoryCache
from ai_portal.gateway.cache.protocol import Cache


class UnknownCacheBackend(Exception):
    """Raised when ``build_cache`` is called with an unregistered name."""


Factory = Callable[..., Cache]

_BACKENDS: dict[str, Factory] = {}


def register_backend(name: str, factory: Factory) -> None:
    """Register a factory under ``name``. Overwrites if already present."""
    _BACKENDS[name] = factory


def build_cache(name: str, **kwargs: Any) -> Cache:
    """Build a cache instance by registered name. ``kwargs`` pass through."""
    factory = _BACKENDS.get(name)
    if factory is None:
        msg = f"unknown cache backend: {name!r} (known: {sorted(_BACKENDS)})"
        raise UnknownCacheBackend(msg)
    return factory(**kwargs)


def _register_bundled() -> None:
    register_backend("inmemory", lambda **kw: InMemoryCache(**kw))

    def _redis(**kw: Any) -> Cache:
        from ai_portal.gateway.cache.backends.redis import RedisCache

        return RedisCache(**kw)

    def _postgres(**kw: Any) -> Cache:
        from ai_portal.gateway.cache.backends.postgres import PostgresCache

        return PostgresCache(**kw)

    register_backend("redis", _redis)
    register_backend("postgres", _postgres)


_register_bundled()
