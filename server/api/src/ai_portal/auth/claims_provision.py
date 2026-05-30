"""JIT user provisioning from verified :class:`UserClaims`.

Shared by social login and directory (LDAP/AD) bind. Given verified claims,
find the local user by email or create one. New users get a personal org so
they can log in immediately (passwordless — their identity is federated).

``org_id`` may be supplied to bind a new user to an existing org (e.g. an LDAP
connection scoped to an org). When absent, a personal org is created.
"""

from __future__ import annotations

import re
import secrets
import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.model import Org, User


class ProvisionError(Exception):
    """Raised when claims cannot be turned into a usable local user."""


def _slugify(email: str) -> str:
    local = email.split("@")[0]
    slug = re.sub(r"[^a-z0-9]", "-", local.lower())[:48]
    return f"{slug}-{secrets.token_hex(4)}"


def provision_from_claims(
    db: Session,
    *,
    claims: UserClaims,
    org_id: _uuid.UUID | None = None,
    default_role: str = "owner",
) -> User:
    """Find or create the local user matching ``claims``.

    - Existing user: reactivated check + name backfill; org untouched unless the
      user has no org and ``org_id`` is supplied.
    - New user: created (passwordless) and bound to ``org_id`` or a fresh
      personal org. Marked verified (identity already federated).
    """
    email = (claims.email or "").strip().lower()
    if not email:
        raise ProvisionError("claims missing email")

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is not None:
        if not user.is_active:
            raise ProvisionError("user account disabled")
        if user.org_id is None and org_id is not None:
            user.org_id = org_id
            user.role = default_role
        if not user.is_verified:
            user.is_verified = True
        if claims.name and not user.name:
            user.name = claims.name
        db.flush()
        return user

    effective_org_id = org_id
    role = default_role
    if effective_org_id is None:
        personal_org = Org(slug=_slugify(email), name=email.split("@")[0])
        db.add(personal_org)
        db.flush()
        effective_org_id = personal_org.id
        role = "owner"

    user = User(
        email=email,
        uuid=_uuid.uuid4(),
        org_id=effective_org_id,
        role=role,
        is_active=True,
        is_verified=True,
        name=claims.name,
    )
    db.add(user)
    db.flush()
    return user
