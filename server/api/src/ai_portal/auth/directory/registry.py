"""Name → factory registry for :class:`DirectoryProvider` implementations.

Providers register at import time::

    from ai_portal.auth.directory.registry import register_directory_provider
    register_directory_provider("ldap", LdapProvider.from_config)

Routes / services look up a provider by ``LdapConnection.kind`` and pass the
decoded connection config dict (host, bind DN, filters, ...).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_portal.auth.directory.protocol import DirectoryProvider

DirectoryProviderFactory = Callable[[dict[str, Any]], DirectoryProvider]


class DirectoryProviderNotFound(Exception):
    """Raised when a kind has no registered factory."""


_REGISTRY: dict[str, DirectoryProviderFactory] = {}


def register_directory_provider(name: str, factory: DirectoryProviderFactory) -> None:
    _REGISTRY[name] = factory


def get_directory_provider(name: str, config: dict[str, Any]) -> DirectoryProvider:
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise DirectoryProviderNotFound(name) from exc
    return factory(config)


def available_directory_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def _clear_for_tests() -> None:
    _REGISTRY.clear()
