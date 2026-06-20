import logging
import uuid as _uuid
from collections.abc import Generator

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.strategies.jwt import decode_token
from ai_portal.auth.strategies.portal_keys import user_for_portal_api_key
from ai_portal.core.config import get_settings
from ai_portal.core.db.rls import set_org_context
from ai_portal.core.db.session import SessionLocal
from ai_portal.auth.model import User

logger = logging.getLogger(__name__)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    user = _authenticate(request, authorization, db)
    # Bind tenant context for RLS-protected tables. Safe to call with None —
    # translates to an empty session var, which makes RLS-protected rows
    # invisible (correct behavior for the rare case of org-less users).
    set_org_context(db, user.org_id)
    request.state.org_id = user.org_id
    return user


def _authenticate(
    request: Request,
    authorization: str | None,
    db: Session,
) -> User:
    settings = get_settings()
    request.state.app_roles = []
    request.state.me_profile = None

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()

    if token.startswith("aip_"):
        user = user_for_portal_api_key(db, token, settings)
        if user is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        return user

    # Enterprise OIDC (selfhosted + oidc_issuer configured): RS256 token → OIDC bearer path.
    if settings.deployment_mode == "selfhosted" and settings.oidc_issuer:
        if token.count(".") == 2 and jwt.get_unverified_header(token).get("alg", "").startswith("RS"):
            from ai_portal.auth.oidc.bearer import authenticate_oidc_bearer
            user, role = authenticate_oidc_bearer(db, token, settings)
            request.state.app_roles = [role]
            return user

    # SaaS / selfhosted local JWT (HS256, our own IdP)
    try:
        payload = decode_token(token, secret=settings.secret_key)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    user_uuid = _uuid.UUID(payload["sub"])
    user = db.scalars(select(User).where(User.uuid == user_uuid)).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")
    sid_raw = payload.get("sid")
    if isinstance(sid_raw, str) and sid_raw:
        try:
            sid_uuid = _uuid.UUID(sid_raw)
            from ai_portal.auth.sessions import is_session_active

            if not is_session_active(db, session_id=sid_uuid):
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, detail="Session revoked"
                )
            request.state.session_id = sid_uuid
        except ValueError:
            pass
    return user


def get_app_roles(request: Request) -> list[str]:
    return list(getattr(request.state, "app_roles", []) or [])


def get_current_org_id(
    user: User = Depends(get_current_user),
) -> _uuid.UUID:
    """Extract org_id from the authenticated user for tenant-scoped queries."""
    if user.org_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="User has no organization assigned.",
        )
    return user.org_id
