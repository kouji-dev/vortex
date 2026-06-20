from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ai_portal.audit.service import emit_audit
from ai_portal.auth import repository as repo
from ai_portal.auth.deps import get_db
from ai_portal.auth.limiter import login_limiter
from ai_portal.auth.schemas import (
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
from ai_portal.auth.model import OrgInvite, User
from sqlalchemy import select

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
    if user.org_id is not None:
        try:
            emit_audit(
                org_id=user.org_id,
                event_type="auth.user.registered",
                actor={"type": "user", "id": user.id, "email": user.email},
                actor_user_id=user.id,
                resource={"type": "user", "id": str(user.uuid) if hasattr(user, "uuid") else user.id},
                payload={"email": user.email},
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
        except Exception:  # noqa: BLE001
            pass
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

    # SSO-required gate (Phase G6): if the user's org enforces SSO, password
    # login is forbidden — they must complete /v1/auth/sso/start instead.
    if user.org_id is not None:
        from ai_portal.auth.sso import is_sso_required

        if is_sso_required(db, org_id=user.org_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "sso_required",
                    "message": "this organization requires SSO login",
                },
            )

    login_limiter.record_success(ip, body.email)
    if user.org_id is not None:
        try:
            emit_audit(
                org_id=user.org_id,
                event_type="auth.user.login",
                actor={"type": "user", "id": user.id, "email": user.email},
                actor_user_id=user.id,
                resource={"type": "user", "id": user.id},
                payload={"email": user.email},
                ip_address=ip,
                user_agent=_user_agent(request),
            )
        except Exception:  # noqa: BLE001
            pass
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


@router.post(
    "/invites/{token}/accept",
    status_code=status.HTTP_200_OK,
    tags=["auth"],
)
def accept_invite_authenticated(
    token: str,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """Accept an org invite as an already-authenticated user.

    The caller must be logged in (bearer access token). The invite's org and
    role are applied to the authenticated user — no password exchange needed.

    Returns 400 if the invite is expired, 409 if already used, 410 if revoked.
    """
    # ── authenticate caller ─────────────────────────────────────────────────
    _require_local_auth()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    raw_token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    try:
        payload = decode_token(raw_token, secret=settings.secret_key)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    try:
        user_uuid = _uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.scalars(select(User).where(User.uuid == user_uuid)).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # ── look up invite ──────────────────────────────────────────────────────
    invite = db.scalars(select(OrgInvite).where(OrgInvite.token == token)).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found")

    # Revoked → 410 Gone
    if invite.revoked_at is not None:
        raise HTTPException(status.HTTP_410_GONE, detail="Invite has been revoked")

    # Already accepted → 409 Conflict
    if invite.accepted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Invite already used")

    # Expired → 400 Bad Request
    if invite.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invite has expired")

    # Email ownership check — invite must be addressed to the authenticated user
    if invite.invited_email.lower() != user.email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invite is for a different email address")

    # ── attach user to org ──────────────────────────────────────────────────
    user.org_id = invite.org_id
    user.role = invite.role
    invite.accepted_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)

    return {"detail": "invite accepted", "org_id": str(invite.org_id), "role": invite.role}

