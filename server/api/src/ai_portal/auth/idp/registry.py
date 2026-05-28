"""Name → factory registry for :class:`IdentityProvider` implementations.

Providers register themselves at import time::

    from ai_portal.auth.idp.registry import register_provider
    register_provider("oidc", OidcProvider.from_config)

Routes look up a provider by ``IdpConnection.kind`` and call its factory
with the connection's decoded config dict.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_portal.auth.idp.protocol import IdentityProvider

IdpProviderFactory = Callable[[dict[str, Any]], IdentityProvider]


class IdpProviderNotFound(Exception):
    """Raised when a kind has no registered factory."""


_REGISTRY: dict[str, IdpProviderFactory] = {}


def register_provider(name: str, factory: IdpProviderFactory) -> None:
    """Register or replace the factory for an IdP kind."""
    _REGISTRY[name] = factory


def get_provider(name: str, config: dict[str, Any]) -> IdentityProvider:
    """Build a provider instance for ``name`` using ``config``."""
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise IdpProviderNotFound(name) from exc
    return factory(config)


def available_providers() -> tuple[str, ...]:
    """Return all registered provider names (sorted for deterministic output)."""
    return tuple(sorted(_REGISTRY))


def _clear_for_tests() -> None:
    """Test helper — wipe the registry. Not part of the public API."""
    _REGISTRY.clear()
