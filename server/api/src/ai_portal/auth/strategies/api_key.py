"""Bearer ``ap_`` API-key authentication strategy.

Resolves an :class:`ai_portal.rbac.service.Actor` for incoming requests
carrying ``Authorization: Bearer ap_xxx``.

Wired in :mod:`ai_portal.control_plane.deps` (``current_actor``) alongside
the existing user-bearer flow. Returns ``None`` for any token that does not
start with the control-plane ``ap_`` prefix so the resolver chain can fall
through to other strategies (JWT / portal keys / entra).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ai_portal.api_keys.model import ApiKey
from ai_portal.api_keys.service import ApiKeyService, PLAINTEXT_PREFIX
from ai_portal.rbac.service import Actor


def looks_like_api_key_token(token: str) -> bool:
    """Cheap discriminator — does *token* carry the ``ap_`` plaintext prefix?"""
    return bool(token) and token.startswith(PLAINTEXT_PREFIX)


def actor_for_api_key_token(db: Session, raw_token: str) -> Actor | None:
    """Resolve an ``Actor`` for a control-plane API key bearer.

    Returns ``None`` if *raw_token* is not an ``ap_`` key OR is invalid,
    revoked, or expired. The :class:`ApiKey.last_used_at` column is bumped on
    successful resolution (see :meth:`ApiKeyService.verify`).

    The resulting actor carries:

    - ``kind = "api_key"``
    - ``api_key_id`` — internal numeric id surrogate via ``int(uuid.int)``? We
      simply expose ``user_id`` when the key has one (personal key), otherwise
      leave it ``None`` (service key).
    - ``org_id`` — owning org of the key.
    """
    if not looks_like_api_key_token(raw_token):
        return None
    row = ApiKeyService(db).verify(raw_token)
    if row is None:
        return None
    return Actor(
        org_id=row.org_id,
        kind="api_key",
        user_id=row.actor_user_id,
        # ``ActorRoleAssignment.actor_api_key_id`` is a plain int column in the
        # legacy RBAC table. The new ``api_keys.id`` is a UUID; we surface a
        # stable int hash so existing assignment lookups still work for now.
        # Cross-table integration lands with the RBAC consolidation task.
        api_key_id=int(row.id.int & ((1 << 63) - 1)),
    )


def api_key_scopes(api_key: ApiKey) -> list[str]:
    """Convenience accessor — return the flat scope list for an api key."""
    return list(api_key.scopes_json or [])
