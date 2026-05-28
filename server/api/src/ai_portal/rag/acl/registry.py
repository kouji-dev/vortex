"""ACL provider registry — connector-kind → provider lookup.

Each connector kind (``gdrive``, ``slack``, ``confluence``, ...) registers
exactly one provider. The ingest pipeline resolves the provider by
``kb_connectors.kind`` when a document is ingested.

A built-in ``default`` provider (see :mod:`ai_portal.rag.acl.idp_mapping`)
handles connector kinds that have no specialised mapper — it treats
``AclSet`` user ids as emails and group ids as opaque group names, doing
best-effort lookups against the IdP mapper.
"""

from __future__ import annotations

from typing import Any


class DuplicateAclProvider(Exception):
    """Raised when a connector_kind is registered twice."""


class UnknownAclProvider(KeyError):
    """Raised when an unknown connector_kind is looked up."""


class _BadAclProvider(Exception):
    """Raised when a class lacks the required ``connector_kind`` attribute."""


_REGISTRY: dict[str, Any] = {}


def register(provider: Any) -> Any:
    """Register an ACL provider instance or class.

    Accepts either an instance (preferred — providers are stateless and can
    take IdP-mapper dependencies via constructor) or a class. Raises on
    missing ``connector_kind`` or duplicate registration.
    """

    kind = getattr(provider, "connector_kind", None)
    if not isinstance(kind, str) or not kind:
        raise _BadAclProvider(
            f"{type(provider).__name__} is missing a non-empty "
            f"'connector_kind' string attribute"
        )
    if kind in _REGISTRY:
        raise DuplicateAclProvider(
            f"acl provider for kind {kind!r} already registered "
            f"as {type(_REGISTRY[kind]).__name__}"
        )
    _REGISTRY[kind] = provider
    return provider


def get(connector_kind: str) -> Any:
    """Return the ACL provider for the given connector kind.

    Falls back to ``"default"`` when the specific kind has no specialised
    provider. Raises :class:`UnknownAclProvider` if neither is registered.
    """

    try:
        return _REGISTRY[connector_kind]
    except KeyError:
        pass
    try:
        return _REGISTRY["default"]
    except KeyError as exc:
        raise UnknownAclProvider(connector_kind) from exc


def registered_kinds() -> tuple[str, ...]:
    """Return all registered kinds, stable-sorted."""

    return tuple(sorted(_REGISTRY))


def _reset_for_tests() -> None:  # pragma: no cover - test helper
    _REGISTRY.clear()
