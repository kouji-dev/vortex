from collections.abc import Generator

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.entra import decode_entra_access_token, roles_from_claims
from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models import User
from ai_portal.services.user_identity import upsert_user_from_entra_claims


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

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()

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
        try:
            claims = decode_entra_access_token(
                token,
                tenant_id=settings.entra_tenant_id,
                audience=settings.entra_api_audience,
            )
            request.state.app_roles = roles_from_claims(claims)
            return upsert_user_from_entra_claims(db, claims)
        except jwt.PyJWTError:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
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
