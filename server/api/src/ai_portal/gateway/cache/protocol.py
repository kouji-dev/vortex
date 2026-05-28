"""Cache backend protocol.

The protocol is deliberately small — three async methods. Backends decide how
to encode the value (JSON-string, native dict, bytes) so callers must not
assume identity; only structural equality is guaranteed.

TTL semantics:

- ``ttl`` is seconds, must be > 0.
- After ``ttl`` elapses, ``get`` MUST return ``None`` and the entry MAY be
  removed lazily on access.
- ``delete`` is idempotent — deleting a missing key is not an error.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    """Pluggable prompt cache backend."""

    name: str

    async def get(self, key: str) -> dict[str, Any] | None:
        """Return the value for ``key`` or ``None`` if missing / expired."""
        ...

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        """Store ``value`` under ``key`` for ``ttl`` seconds."""
        ...

    async def delete(self, key: str) -> None:
        """Remove ``key`` if present. No-op if missing."""
        ...
