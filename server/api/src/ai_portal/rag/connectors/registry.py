"""Connector registry — name → connector class lookup.

Adapters call :func:`register` at import time. Resolvers call :func:`get`
to instantiate by ``kb_connectors.kind`` value. Registration is strict —
duplicates raise to prevent silent rebinding of a kind.
"""

from __future__ import annotations

from typing import Any

from ai_portal.rag.connectors.manifest import ConnectorManifest


class DuplicateConnector(Exception):
    """Raised when a connector name is registered twice."""


class UnknownConnector(KeyError):
    """Raised when a name is not in the registry."""


class _BadConnector(Exception):
    """Raised when a class is missing the required manifest attribute."""


_REGISTRY: dict[str, type[Any]] = {}


def register(cls: type[Any]) -> type[Any]:
    """Register a connector class. Returns the class (decorator-friendly).

    Raises :class:`_BadConnector` if the class lacks a ``manifest`` attribute
    of type :class:`ConnectorManifest`, and :class:`DuplicateConnector` if
    the manifest name is already taken.
    """

    manifest = getattr(cls, "manifest", None)
    if not isinstance(manifest, ConnectorManifest):
        raise _BadConnector(
            f"{cls.__name__} is missing a ConnectorManifest 'manifest' attribute"
        )
    if manifest.name in _REGISTRY:
        raise DuplicateConnector(
            f"connector {manifest.name!r} already registered "
            f"as {_REGISTRY[manifest.name].__name__}"
        )
    _REGISTRY[manifest.name] = cls
    return cls


def get(name: str) -> type[Any]:
    """Return the connector class registered under ``name``."""

    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise UnknownConnector(name) from exc


def registered_names() -> tuple[str, ...]:
    """Return all registered connector names (stable, sorted)."""

    return tuple(sorted(_REGISTRY))


def _reset_for_tests() -> None:  # pragma: no cover - test helper
    _REGISTRY.clear()
