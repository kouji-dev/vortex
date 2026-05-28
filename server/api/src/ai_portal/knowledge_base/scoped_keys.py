"""Per-KB scoped API key minter.

Wraps ``control_plane.ApiKeyService`` and binds the resulting key to a
single KB id via the ``scopes_json`` list. Lookup helpers resolve a key
back to the KB it can operate on.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api_keys.model import ApiKey
from ai_portal.api_keys.service import ApiKeyService, CreatedApiKey

# Scope tokens carried in ``ApiKey.scopes_json``.
SCOPE_KB_READ = "kb:read"
SCOPE_KB_ANSWER = "kb:answer"

KB_RESOURCE_PREFIX = "kb:"


@dataclass(frozen=True)
class ScopedKbKey:
    plaintext: str
    key_id: _uuid.UUID
    kb_id: int
    scopes: tuple[str, ...]


def _kb_resource_token(kb_id: int) -> str:
    return f"{KB_RESOURCE_PREFIX}{kb_id}"


def mint_scoped_kb_key(
    db: Session,
    *,
    org_id: _uuid.UUID,
    kb_id: int,
    name: str = "",
    actor_user_id: int | None = None,
    extra_scopes: tuple[str, ...] = (),
) -> ScopedKbKey:
    """Mint a read-only API key bound to a single KB.

    Scopes:
        - ``kb:read`` / ``kb:answer``: capability tokens.
        - ``kb:<id>``                 : resource binding.
    """
    scopes = [SCOPE_KB_READ, SCOPE_KB_ANSWER, _kb_resource_token(kb_id), *extra_scopes]
    svc = ApiKeyService(db)
    created: CreatedApiKey = svc.create(
        org_id=org_id,
        name=name or f"kb-{kb_id}",
        scopes=scopes,
        actor_user_id=actor_user_id,
    )
    return ScopedKbKey(
        plaintext=created.plaintext,
        key_id=created.key.id,
        kb_id=kb_id,
        scopes=tuple(scopes),
    )


def kb_id_for_key(key: ApiKey) -> int | None:
    """Return the bound KB id encoded in ``key.scopes_json`` or ``None``."""
    for token in key.scopes_json or ():
        if isinstance(token, str) and token.startswith(KB_RESOURCE_PREFIX):
            tail = token[len(KB_RESOURCE_PREFIX) :]
            if tail.isdigit():
                return int(tail)
    return None


def key_permits(key: ApiKey, scope: str, *, kb_id: int) -> bool:
    """Permission check: scope present AND key bound to ``kb_id``."""
    scopes = set(key.scopes_json or ())
    return scope in scopes and _kb_resource_token(kb_id) in scopes


def list_scoped_kb_keys(
    db: Session,
    *,
    org_id: _uuid.UUID,
    kb_id: int,
    include_revoked: bool = False,
) -> Sequence[ApiKey]:
    """List API keys bound to ``kb_id`` within ``org_id``."""
    stmt = select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.created_at.desc())
    rows = list(db.scalars(stmt))
    token = _kb_resource_token(kb_id)
    out: list[ApiKey] = []
    for r in rows:
        scopes = r.scopes_json or []
        if token not in scopes:
            continue
        if not include_revoked and r.revoked_at is not None:
            continue
        out.append(r)
    return out


def get_scoped_kb_key(
    db: Session,
    *,
    org_id: _uuid.UUID,
    kb_id: int,
    key_id: _uuid.UUID,
) -> ApiKey | None:
    """Return a single KB-scoped key or ``None`` if not bound to ``kb_id``."""
    row = db.scalars(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.org_id == org_id)
    ).first()
    if row is None:
        return None
    if _kb_resource_token(kb_id) not in (row.scopes_json or ()):
        return None
    return row
