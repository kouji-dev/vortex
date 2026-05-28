"""Registry for search providers.

Providers are registered lazily — the class object is registered, then a
provider instance is built on demand via ``get_provider(name)``. This keeps
optional SDK imports out of the import graph until used.
"""
from __future__ import annotations

from typing import Callable

from ai_portal.rag.search_providers.protocol import SearchProvider


class UnknownSearchProvider(KeyError):
    """Raised when get_provider() receives an unknown name."""


_FACTORIES: dict[str, Callable[..., SearchProvider]] = {}


def register(name: str, factory: Callable[..., SearchProvider]) -> None:
    """Register a factory that builds a provider on demand."""
    key = name.lower().strip()
    if key in _FACTORIES:
        raise ValueError(f"search provider already registered: {key}")
    _FACTORIES[key] = factory


def get_provider(name: str, **kwargs) -> SearchProvider:
    key = name.lower().strip()
    factory = _FACTORIES.get(key)
    if not factory:
        raise UnknownSearchProvider(name)
    return factory(**kwargs)


def list_providers() -> list[str]:
    return sorted(_FACTORIES)


def _register_bundled() -> None:
    """Wire up all bundled providers."""
    from ai_portal.rag.search_providers.providers.bing import BingProvider
    from ai_portal.rag.search_providers.providers.brave import BraveProvider
    from ai_portal.rag.search_providers.providers.exa import ExaProvider
    from ai_portal.rag.search_providers.providers.google_cse import GoogleCseProvider
    from ai_portal.rag.search_providers.providers.internal_kbs import (
        InternalKbsProvider,
    )
    from ai_portal.rag.search_providers.providers.tavily import TavilyProvider

    register("tavily", lambda **kw: TavilyProvider(**kw))
    register("exa", lambda **kw: ExaProvider(**kw))
    register("brave", lambda **kw: BraveProvider(**kw))
    register("bing", lambda **kw: BingProvider(**kw))
    register("google_cse", lambda **kw: GoogleCseProvider(**kw))
    register("internal_kbs", lambda **kw: InternalKbsProvider(**kw))


_register_bundled()
