"""IdP mapping — best-effort source ID → org ID resolution.

Connectors emit ``AclSet`` populated with **source-native** identifiers:

- Email addresses (``alice@acme.com``)
- IdP object IDs (Google sub, OIDC sub, etc.)
- Group external IDs

This module resolves them against the org's user table and returns a
:class:`ResolvedAcl`. Anything that cannot be resolved goes into
:attr:`ResolvedAcl.unresolved` so a future re-sync can fill in the
missing IDs without re-ingesting.

The default mapping rules:

- A source user id that looks like an email matches ``users.email``.
- A source user id that is a UUID matches ``users.uuid``.
- Group ids: no group resolver is wired (SCIM removed); goes to unresolved.

All matches are scoped by ``org_id`` — never cross-tenant.
"""

from __future__ import annotations

import re
import uuid as _uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.model import User
from ai_portal.rag.acl.protocol import ResolvedAcl
from ai_portal.rag.connectors.protocol import AclSet

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _looks_like_email(s: str) -> bool:
    return bool(_EMAIL_RE.match(s))


def _looks_like_uuid(s: str) -> bool:
    return bool(_UUID_RE.match(s))


@dataclass
class IdpMapper:
    """Best-effort resolver scoped to a single org.

    Stateless — pass a fresh SQLAlchemy session in for each call. We avoid
    caching here; the ingest pipeline batches lookups via
    :meth:`map_acls` which loads users/groups once per AclSet.
    """

    db: Session
    org_id: _uuid.UUID | str

    def _coerce_org_id(self) -> _uuid.UUID:
        if isinstance(self.org_id, _uuid.UUID):
            return self.org_id
        return _uuid.UUID(str(self.org_id))

    # ------------------------------------------------------------------ users

    def resolve_user(self, source_user_id: str) -> str | None:
        """Return the internal ``users.id`` (as string) or ``None``."""

        org_uuid = self._coerce_org_id()
        if _looks_like_email(source_user_id):
            row = self.db.execute(
                select(User.id).where(
                    User.email == source_user_id.lower(),
                    User.org_id == org_uuid,
                )
            ).first()
            if row is None:
                # Try non-lowercased — User.email is stored canonical-cased.
                row = self.db.execute(
                    select(User.id).where(
                        User.email == source_user_id,
                        User.org_id == org_uuid,
                    )
                ).first()
            if row is not None:
                return str(row[0])
            return None

        if _looks_like_uuid(source_user_id):
            row = self.db.execute(
                select(User.id).where(
                    User.uuid == _uuid.UUID(source_user_id),
                    User.org_id == org_uuid,
                )
            ).first()
            if row is not None:
                return str(row[0])
            return None

        return None

    # ----------------------------------------------------------------- groups

    def resolve_group(self, source_group_id: str) -> str | None:
        """Return the internal group id (as string) or ``None``.

        OIDC group resolution uses an identity match: the connector group id
        must equal the IdP group name stored in ``users.idp_groups``.
        Returns ``source_group_id`` unchanged so ACL membership checks compare
        the raw group name directly against ``user.idp_groups``.
        """
        return source_group_id

    # ---------------------------------------------------------------- AclSet

    def map_acls(self, source_acls: AclSet) -> ResolvedAcl:
        """Resolve every member of an :class:`AclSet` into a :class:`ResolvedAcl`.

        Unresolved entries are kept so a later re-sync (after SCIM catches
        up) can fill them in.
        """

        out = ResolvedAcl(public=source_acls.public)
        for src in source_acls.user_ids:
            mapped = self.resolve_user(src)
            if mapped is None:
                out.unresolved.add(f"user:{src}")
            else:
                out.user_ids.add(mapped)
        for src in source_acls.group_ids:
            mapped = self.resolve_group(src)
            if mapped is None:
                out.unresolved.add(f"group:{src}")
            else:
                out.group_ids.add(mapped)
        return out


# ----------------------------------------------------------- bundled provider


class DefaultIdpAclProvider:
    """Default ACL provider — pure IdP mapping, no connector-specific quirks.

    Registered under kind ``"default"`` so any connector without a
    specialised provider still gets best-effort resolution.
    """

    connector_kind = "default"

    def __init__(self, db: Session) -> None:
        self._db = db

    async def map(self, source_acls: AclSet, org_id: str) -> ResolvedAcl:
        mapper = IdpMapper(db=self._db, org_id=org_id)
        return mapper.map_acls(source_acls)
