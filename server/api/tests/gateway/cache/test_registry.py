"""Cache registry — name → factory; settings-driven selection."""

from __future__ import annotations

import pytest

from ai_portal.gateway.cache import (
    Cache,
    InMemoryCache,
    UnknownCacheBackend,
    build_cache,
    register_backend,
)


def test_build_inmemory_by_name() -> None:
    cache = build_cache("inmemory")
    assert isinstance(cache, InMemoryCache)
    assert isinstance(cache, Cache)


def test_build_unknown_backend_raises() -> None:
    with pytest.raises(UnknownCacheBackend):
        build_cache("does-not-exist")


def test_register_backend_then_build() -> None:
    class _Dummy:
        name = "dummy"

        async def get(self, key):  # pragma: no cover - shape only
            return None

        async def set(self, key, value, ttl):  # pragma: no cover
            return None

        async def delete(self, key):  # pragma: no cover
            return None

    register_backend("dummy-test", lambda **_: _Dummy())
    try:
        built = build_cache("dummy-test")
        assert built.name == "dummy"
    finally:
        # registry cleanup so this test is order-independent
        from ai_portal.gateway.cache import registry

        registry._BACKENDS.pop("dummy-test", None)


def test_build_passes_kwargs_to_factory() -> None:
    seen: dict = {}

    def factory(**kwargs):
        seen.update(kwargs)
        return InMemoryCache()

    register_backend("kw-test", factory)
    try:
        build_cache("kw-test", foo="bar", num=3)
        assert seen == {"foo": "bar", "num": 3}
    finally:
        from ai_portal.gateway.cache import registry

        registry._BACKENDS.pop("kw-test", None)
