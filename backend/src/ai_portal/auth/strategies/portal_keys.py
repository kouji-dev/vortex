from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.core.config import Settings
from ai_portal.models import User
from ai_portal.models.user_portal_api_key import UserPortalApiKey


def hash_portal_api_key(raw_token: str, pepper: str) -> str:
    if pepper.strip():
        return hmac.new(
            pepper.encode("utf-8"),
            raw_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    # Dev / tests only — set PORTAL_API_KEY_PEPPER in any shared environment.
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_portal_api_key(
    db: Session,
    *,
    user_id: int,
    label: str | None,
    pepper: str,
) -> tuple[UserPortalApiKey, str]:
    raw = "aip_" + secrets.token_urlsafe(32)
    rec = UserPortalApiKey(
        user_id=user_id,
        label=(label.strip()[:128] if label else None) or None,
        key_hash=hash_portal_api_key(raw, pepper),
        key_prefix=raw[:16],
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec, raw


def user_for_portal_api_key(
    db: Session,
    raw_token: str,
    settings: Settings,
) -> User | None:
    if not raw_token.startswith("aip_"):
        return None
    digest = hash_portal_api_key(raw_token, settings.portal_api_key_pepper)
    row = db.scalars(
        select(UserPortalApiKey).where(
            UserPortalApiKey.key_hash == digest,
            UserPortalApiKey.revoked_at.is_(None),
        )
    ).first()
    if row is None:
        return None
    row.last_used_at = datetime.now(UTC)
    db.commit()
    user = db.get(User, row.user_id)
    return user


def list_keys_for_user(db: Session, user_id: int) -> list[UserPortalApiKey]:
    return list(
        db.scalars(
            select(UserPortalApiKey)
            .where(UserPortalApiKey.user_id == user_id)
            .order_by(UserPortalApiKey.created_at.desc())
        ).all()
    )


def revoke_key(db: Session, *, user_id: int, key_id: int) -> bool:
    row = db.get(UserPortalApiKey, key_id)
    if row is None or row.user_id != user_id or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(UTC)
    db.commit()
    return True
