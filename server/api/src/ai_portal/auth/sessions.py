"""User session persistence — list, revoke, current-session marker.

Phase M2 of the Control Plane plan. Each successful login mints a
:class:`UserSession` row keyed by ``sha256(refresh_token)``. Routes use the
``sid`` claim baked into the access token to flag "this is your current
session" in listings.
"""
from __future__ import annotations

import hashlib
import uuid as _uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.model import UserSession

DEFAULT_SESSION_EXPIRY_DAYS = 30


class SessionNotFound(Exception):
    pass


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    db: Session,
    *,
    user_id: int,
    refresh_token: str,
    ip: str | None,
    user_agent: str | None,
    session_id: _uuid.UUID | None = None,
    expires_in_days: int = DEFAULT_SESSION_EXPIRY_DAYS,
) -> UserSession:
    session = UserSession(
        id=session_id or _uuid.uuid4(),
        user_id=user_id,
        token_hash=hash_refresh_token(refresh_token),
        ip=ip,
        user_agent=user_agent,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, *, user_id: int) -> list[UserSession]:
    return list(
        db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.created_at.desc())
        ).all()
    )


def revoke_session(db: Session, *, user_id: int, session_id: _uuid.UUID) -> None:
    row = db.scalars(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
        )
    ).first()
    if row is None:
        raise SessionNotFound(str(session_id))
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        db.commit()


def revoke_all_except(
    db: Session, *, user_id: int, keep_session_id: _uuid.UUID | None
) -> int:
    rows = db.scalars(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    ).all()
    revoked = 0
    now = datetime.now(UTC)
    for row in rows:
        if keep_session_id is not None and row.id == keep_session_id:
            continue
        row.revoked_at = now
        revoked += 1
    if revoked:
        db.commit()
    return revoked


def is_session_active(db: Session, *, session_id: _uuid.UUID) -> bool:
    row = db.get(UserSession, session_id)
    if row is None or row.revoked_at is not None:
        return False
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > datetime.now(UTC)
