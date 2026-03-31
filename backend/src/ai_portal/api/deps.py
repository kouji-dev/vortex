import logging
from collections.abc import Generator

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.entra import decode_entra_access_token, roles_from_claims
from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models import User
from ai_portal.services.portal_api_keys import user_for_portal_api_key
from ai_portal.services.user_identity import (
    profile_fields_from_claims,
    upsert_user_from_entra_claims,
)

logger = logging.getLogger(__name__)


def _looks_like_compact_jws(token: str) -> bool:
    """Entra access tokens are JWS compact form: header.payload.signature (3 segments)."""
    parts = token.split(".")
    return len(parts) == 3 and all(len(p) > 0 for p in parts)


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

    if settings.auth_mode == "dev":
        if token != settings.dev_bearer_token:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        user = db.scalars(
            select(User).where(User.email == settings.dev_seed_user_email)
        ).first()
        if user is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Dev user not found; run alembic upgrade head",
            )
        return user

    if settings.auth_mode == "entra":
        if not settings.entra_tenant_id or not settings.entra_api_audience:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Entra auth misconfigured (tenant or audience)",
            )
        if not _looks_like_compact_jws(token):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Bearer token is not a JWT; this API is running with AUTH_MODE=entra. "
                    "Send a Microsoft Entra access token for your API scope, or set AUTH_MODE=dev "
                    "(and restart) to use DEV_BEARER_TOKEN from the SPA."
                ),
            )
        try:
            claims = decode_entra_access_token(
                token,
                tenant_id=settings.entra_tenant_id,
                audience=settings.entra_api_audience,
            )
            request.state.app_roles = roles_from_claims(claims)
            request.state.me_profile = profile_fields_from_claims(claims)
            return upsert_user_from_entra_claims(db, claims)
        except jwt.PyJWTError as e:
            logger.warning("Entra JWT rejected: %s", e)
            detail = (
                f"Invalid or expired token: {e}"
                if settings.entra_debug_jwt
                else "Invalid or expired token"
            )
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail=detail,
            ) from None
        except ValueError as e:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
            ) from e

    raise HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unknown auth_mode",
    )


def get_app_roles(request: Request) -> list[str]:
    return list(getattr(request.state, "app_roles", []) or [])
