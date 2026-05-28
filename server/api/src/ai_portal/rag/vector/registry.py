"""VectorStore registry.

Backends register under a stable name; the resolver looks them up.
"""

from __future__ import annotations

from typing import Callable

from ai_portal.rag.vector.protocol import VectorStore


class UnknownVectorBackend(KeyError):
    """Raised when a backend name has no registered factory."""


class DuplicateBackend(ValueError):
    """Raised on duplicate ``register`` calls for the same name."""


Factory = Callable[[dict | None], VectorStore]

_REGISTRY: dict[str, Factory] = {}


def register(name: str, factory: Factory) -> None:
    if name in _REGISTRY:
        raise DuplicateBackend(name)
    _REGISTRY[name] = factory


def get(name: str, config: dict | None = None) -> VectorStore:
    try:
        factory = _REGISTRY[name]
    except KeyError as e:
        raise UnknownVectorBackend(name) from e
    return factory(config or {})


def names() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def _reset_for_tests() -> None:
    """Clear the registry (test-only helper)."""
    _REGISTRY.clear()
