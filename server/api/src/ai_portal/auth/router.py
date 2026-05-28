from __future__ import annotations

import uuid as _uuid

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ai_portal.auth import repository as repo
from ai_portal.auth.deps import get_db
from ai_portal.auth.limiter import login_limiter
from ai_portal.auth.mfa_totp import (
    InvalidTotpCode,
    MfaFactorNotFound,
    MfaService,
    user_has_confirmed_totp,
)
from ai_portal.auth.schemas import (
    AcceptInviteRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)
from ai_portal.auth.sessions import create_session
from ai_portal.auth.strategies.dev import AuthenticationError, RegistrationError, UserManager
from ai_portal.auth.strategies.jwt import decode_token
from ai_portal.core.config import get_settings
from ai_portal.auth.model import User

router = APIRouter(prefix="/auth", tags=["auth"])


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


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "-"


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _issue_session_tokens(
    manager: UserManager,
    user: User,
    db: Session,
    *,
    request: Request,
) -> TokenResponse:
    # Mint session UUID up-front and bake it into the JWT ``sid`` claim — that
    # way the refresh-token hash (which we persist as the session row key) is
    # already unique across logins minted in the same second.
    session_id = _uuid.uuid4()
    final = manager.create_tokens(user, session_id=session_id)
    create_session(
        db,
        user_id=user.id,
        session_id=session_id,
        refresh_token=final["refresh_token"],
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return TokenResponse(**final)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
def register(
    body: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    _require_local_auth()
    _require_signup_open()
    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    try:
        user = manager.register(email=body.email, password=body.password)
    except RegistrationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    return _issue_session_tokens(manager, user, db, request=request)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    _require_local_auth()
    ip = _client_ip(request)
    retry_after = login_limiter.check(ip, body.email)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too_many_login_attempts",
            headers={"Retry-After": str(retry_after)},
        )
    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    try:
        user = manager.authenticate(email=body.email, password=body.password)
    except AuthenticationError as e:
        login_limiter.record_failure(ip, body.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(e))

    # MFA gate: confirmed TOTP factor → require totp_code.
    if user_has_confirmed_totp(db, user.id):
        if not body.totp_code:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail={"error": "mfa_required", "factor": "totp"},
            )
        try:
            MfaService(db).check_login_totp(user_id=user.id, code=body.totp_code)
        except (InvalidTotpCode, MfaFactorNotFound):
            login_limiter.record_failure(ip, body.email)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_totp_code"},
            )

    login_limiter.record_success(ip, body.email)
    return _issue_session_tokens(manager, user, db, request=request)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    body: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
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
    return _issue_session_tokens(manager, user, db, request=request)


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
    user = repo.get_user_by_uuid(db, user_uuid)
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


@router.post("/accept-invite", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Accept an org invite and create an account (or migrate an existing one)."""
    from datetime import UTC, datetime

    invite = repo.get_pending_invite_by_token(db, body.token)
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found or expired")
    if invite.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, detail="Invite has expired")

    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)

    # Check if user already exists (migrate) or create new
    existing_user = repo.get_user_by_email(db, invite.invited_email)

    if existing_user:
        # Migrate to new org — archive old personal org if it exists
        old_org = repo.get_personal_org_for_user(db, existing_user)
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

    repo.accept_invite_and_commit(db, invite, user)
    return _issue_session_tokens(manager, user, db, request=request)
