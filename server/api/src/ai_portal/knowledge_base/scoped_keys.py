"""Per-KB scoped API key minter.

Wraps ``control_plane.ApiKeyService`` and binds the resulting key to a
single KB id via the ``scopes_json`` list. Lookup helpers resolve a key
back to the KB it can operate on.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass

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
