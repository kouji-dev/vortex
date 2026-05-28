from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30
ALGORITHM = "HS256"


def create_access_token(
    *,
    user_uuid: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    secret: str,
    expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES,
    session_id: uuid.UUID | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict = {
        "sub": str(user_uuid),
        "org_id": str(org_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    if session_id is not None:
        payload["sid"] = str(session_id)
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_refresh_token(
    *,
    user_uuid: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    secret: str,
    expires_days: int = REFRESH_TOKEN_EXPIRE_DAYS,
    session_id: uuid.UUID | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict = {
        "sub": str(user_uuid),
        "org_id": str(org_id),
        "role": role,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    if session_id is not None:
        payload["sid"] = str(session_id)
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, *, secret: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, secret, algorithms=[ALGORITHM])
