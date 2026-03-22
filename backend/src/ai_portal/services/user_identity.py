from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import User


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def email_from_claims(claims: dict[str, Any]) -> str | None:
    for key in ("preferred_username", "email", "upn"):
        v = claims.get(key)
        if isinstance(v, str) and v.strip():
            return _normalize_email(v)
    return None


def upsert_user_from_entra_claims(db: Session, claims: dict[str, Any]) -> User:
    oid = claims.get("oid")
    if isinstance(oid, str):
        oid = oid.strip() or None
    else:
        oid = None

    email = email_from_claims(claims)
    if not email and not oid:
        msg = "Token missing oid and a usable email claim"
        raise ValueError(msg)

    user: User | None = None
    if oid:
        user = db.scalars(select(User).where(User.entra_object_id == oid)).first()

    if user is None and email:
        user = db.scalars(select(User).where(User.email == email)).first()

    if user is None:
        if not email:
            msg = "Cannot create user without email claim"
            raise ValueError(msg)
        user = User(email=email, entra_object_id=oid)
        db.add(user)
        db.flush()
        return user

    if oid and user.entra_object_id != oid:
        user.entra_object_id = oid
    if email and user.email != email:
        user.email = email
    db.flush()
    return user
