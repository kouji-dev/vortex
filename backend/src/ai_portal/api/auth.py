from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_db
from ai_portal.auth.jwt import decode_token
from ai_portal.auth.manager import AuthenticationError, RegistrationError, UserManager
from ai_portal.config import get_settings
from ai_portal.models.org import Org
from ai_portal.models.org_invite import OrgInvite
from ai_portal.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    email: str
    role: str
    is_verified: bool
    is_superuser: bool
    org_id: str | None

    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require_local_auth() -> None:
    settings = get_settings()
    if settings.deployment_mode not in ("saas", "selfhosted"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Local auth is only available when DEPLOYMENT_MODE=saas or selfhosted",
        )


def _require_signup_open() -> None:
    settings = get_settings()
    if settings.deployment_mode == "selfhosted":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Open signup is disabled. Use an invite link.",
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    _require_local_auth()
    _require_signup_open()
    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    try:
        user = manager.register(email=body.email, password=body.password)
    except RegistrationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    tokens = manager.create_tokens(user)
    return TokenResponse(**tokens)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    _require_local_auth()
    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    try:
        user = manager.authenticate(email=body.email, password=body.password)
    except AuthenticationError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(e))
    tokens = manager.create_tokens(user)
    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    _require_local_auth()
    settings = get_settings()
    try:
        payload = decode_token(body.refresh_token, secret=settings.secret_key)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")
    user_uuid = _uuid.UUID(payload["sub"])
    manager = UserManager(db=db, secret=settings.secret_key)
    user = manager.get_by_uuid(user_uuid)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")
    tokens = manager.create_tokens(user)
    return TokenResponse(**tokens)


@router.get("/me", response_model=UserRead)
def auth_me(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> UserRead:
    """Lightweight identity endpoint for local auth mode."""
    _require_local_auth()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    try:
        payload = decode_token(token, secret=settings.secret_key)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_uuid = _uuid.UUID(payload["sub"])
    user = db.scalars(select(User).where(User.uuid == user_uuid)).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return UserRead(
        id=user.id,
        email=user.email,
        role=user.role,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        org_id=str(user.org_id) if user.org_id else None,
    )


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


@router.post("/accept-invite", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
def accept_invite(body: AcceptInviteRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Accept an org invite and create an account (or migrate an existing one)."""
    invite = db.scalars(
        select(OrgInvite).where(
            OrgInvite.token == body.token,
            OrgInvite.accepted_at == None,  # noqa: E711
            OrgInvite.revoked_at == None,  # noqa: E711
        )
    ).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found or expired")
    if invite.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, detail="Invite has expired")

    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)

    # Check if user already exists (migrate) or create new
    existing_user = db.scalars(
        select(User).where(User.email == invite.invited_email)
    ).first()

    if existing_user:
        # Migrate to new org — archive old personal org if it exists
        old_org = db.scalars(
            select(Org).where(
                Org.id == existing_user.org_id,
                Org.instance_mode == False,  # noqa: E712
            )
        ).first()
        if old_org and old_org.slug.startswith(existing_user.email.split("@")[0]):
            old_org.archived_at = datetime.now(UTC)
        existing_user.org_id = invite.org_id
        existing_user.role = invite.role
        user = existing_user
    else:
        try:
            user = manager.register(
                email=invite.invited_email,
                password=body.password,
                org_id=invite.org_id,
                role=invite.role,
            )
        except RegistrationError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))

    invite.accepted_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    tokens = manager.create_tokens(user)
    return TokenResponse(**tokens)
