"""User session persistence — list, revoke, current-session marker.

Phase M2 of the Control Plane plan. Each successful login mints a
:class:`UserSession` row keyed by ``sha256(refresh_token)``. Routes use the
``sid`` claim baked into the access token to flag "this is your current
session" in listings.
"""
from __future__ import annotations

import hashlib
import logging
import uuid as _uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.model import UserSession

DEFAULT_SESSION_EXPIRY_DAYS = 30
NEW_DEVICE_LOOKBACK_DAYS = 30

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):
    pass


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ua_fingerprint(user_agent: str | None) -> str:
    """Hash the user-agent — opaque, cheap, comparable."""
    return hashlib.sha256((user_agent or "").encode("utf-8")).hexdigest()[:16]


def is_new_device(
    db: Session,
    *,
    user_id: int,
    ip: str | None,
    user_agent: str | None,
    lookback_days: int = NEW_DEVICE_LOOKBACK_DAYS,
) -> bool:
    """Return True if no session in the lookback window matches (ip, UA fingerprint).

    Both ``ip`` and ``user_agent`` are matched against persisted session rows.
    A blank IP or UA still produces a deterministic fingerprint so that the
    "absent → match against another absent" case behaves consistently.
    """
    since = datetime.now(UTC) - timedelta(days=lookback_days)
    fp = _ua_fingerprint(user_agent)
    rows = db.scalars(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.created_at >= since,
        )
    ).all()
    for row in rows:
        if row.ip == ip and _ua_fingerprint(row.user_agent) == fp:
            return False
    return True


# ── New-device notification hook ────────────────────────────────────────────
#
# Module-level callable, defaults to a no-op. The application wiring (see
# ``ai_portal.main``) replaces this with a function that invokes the
# NotifyService. Keeping the hook lightweight prevents the session module from
# depending on the notify subsystem at import time.

NewDeviceHook = Callable[[int, str | None, str | None, datetime], None]


def _default_new_device_hook(
    user_id: int, ip: str | None, user_agent: str | None, ts: datetime
) -> None:
    logger.info(
        "auth.login.new_device user_id=%s ip=%s ua=%s ts=%s",
        user_id, ip, user_agent, ts.isoformat(),
    )


_new_device_hook: NewDeviceHook = _default_new_device_hook


def set_new_device_hook(hook: NewDeviceHook | None) -> None:
    """Replace the new-device hook (None resets to the logger default)."""
    global _new_device_hook
    _new_device_hook = hook or _default_new_device_hook


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
    # Detect new device BEFORE inserting the row — otherwise the freshly
    # inserted session would always match itself.
    new_device = is_new_device(db, user_id=user_id, ip=ip, user_agent=user_agent)
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
    if new_device:
        try:
            _new_device_hook(user_id, ip, user_agent, datetime.now(UTC))
        except Exception:  # pragma: no cover — hooks must not break login
            logger.exception("new_device_hook_failed user_id=%s", user_id)
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
