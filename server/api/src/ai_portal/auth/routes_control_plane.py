"""Control-plane HTTP surface: signup, email verify, password reset, profile,
and org membership endpoints. Builds on :mod:`auth.users_service` +
:mod:`auth.orgs_service`. Legacy `/auth/register` and `/api/orgs/*` remain in
their existing routers — these endpoints live under `/v1/...` to match the
spec and avoid colliding with the legacy surface.
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.limiter import password_reset_limiter
from ai_portal.auth.model import User
from ai_portal.auth.orgs_schemas import (
    OrgCreate,
    OrgInviteCreate,
    OrgInviteOut,
    OrgMemberOut,
    OrgOut,
    OrgUpdate,
)
from ai_portal.auth.orgs_service import (
    InviteExpired,
    InviteNotFound,
    NotAMember,
    OrgNotArchived,
    OrgNotFound,
    OrgRestoreWindowExpired,
    OrgService,
    OrgSlugTaken,
)
from ai_portal.auth.users_schemas import (
    PasswordResetConfirm,
    PasswordResetRequest,
    SignupRequest,
    UpdateProfileRequest,
    UserProfileOut,
    VerifyEmailRequest,
)
from ai_portal.auth.users_service import (
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidToken,
    TokenExpired,
    UserNotFound,
    UserService,
)

router = APIRouter(prefix="/v1", tags=["control-plane"])


# ── helpers ──────────────────────────────────────────────────────────────────


def _org_out(org) -> OrgOut:
    return OrgOut(
        id=str(org.id),
        slug=org.slug,
        name=org.name,
        region=org.region,
        status=org.status,
        instance_mode=org.instance_mode,
        created_at=org.created_at,
    )


def _invite_out(inv) -> OrgInviteOut:
    return OrgInviteOut(
        id=inv.id,
        org_id=str(inv.org_id),
        invited_email=inv.invited_email,
        role=inv.role,
        expires_at=inv.expires_at,
        created_at=inv.created_at,
    )


def _member_out(m) -> OrgMemberOut:
    return OrgMemberOut(
        id=m.id,
        org_id=str(m.org_id),
        user_id=m.user_id,
        role=m.role,
        created_at=m.created_at,
    )


def _profile_out(u: User) -> UserProfileOut:
    return UserProfileOut(
        id=u.id,
        email=u.email,
        name=u.name,
        locale=u.locale,
        role=u.role,
        is_active=u.is_active,
        is_verified=u.is_verified,
        email_verified_at=u.email_verified_at,
        org_id=str(u.org_id) if u.org_id else None,
    )


# ── Users ────────────────────────────────────────────────────────────────────


@router.post("/users/signup", status_code=status.HTTP_201_CREATED, response_model=UserProfileOut)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> UserProfileOut:
    try:
        user = UserService(db).signup(body)
    except EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered") from None
    return _profile_out(user)


@router.post("/users/verify-email", response_model=UserProfileOut)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)) -> UserProfileOut:
    try:
        user = UserService(db).verify_email(body)
    except InvalidToken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid token") from None
    except TokenExpired:
        raise HTTPException(status.HTTP_410_GONE, detail="Token expired") from None
    except UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found") from None
    return _profile_out(user)


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "-"


@router.post("/users/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def password_reset_request(
    body: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    # Always 202 — do not leak whether the email exists.
    ip = _client_ip(request)
    retry_after = password_reset_limiter.check(ip, body.email)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too_many_password_reset_requests",
            headers={"Retry-After": str(retry_after)},
        )
    password_reset_limiter.record_failure(ip, body.email)
    UserService(db).request_password_reset(body)
    return {"status": "accepted"}


@router.post("/users/password-reset/confirm", response_model=UserProfileOut)
def password_reset_confirm(
    body: PasswordResetConfirm,
    request: Request,
    db: Session = Depends(get_db),
) -> UserProfileOut:
    ip = _client_ip(request)
    # Identifier is the token prefix — bucket per (ip, token) so brute-forcing
    # token guesses gets throttled without leaking the token to logs.
    key = body.token[:16]
    retry_after = password_reset_limiter.check(ip, key)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too_many_password_reset_attempts",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        user = UserService(db).reset_password(body)
    except InvalidToken:
        password_reset_limiter.record_failure(ip, key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid token") from None
    except TokenExpired:
        password_reset_limiter.record_failure(ip, key)
        raise HTTPException(status.HTTP_410_GONE, detail="Token expired") from None
    except UserNotFound:
        password_reset_limiter.record_failure(ip, key)
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found") from None
    password_reset_limiter.record_success(ip, key)
    return _profile_out(user)


@router.get("/users/me", response_model=UserProfileOut)
def get_my_profile(user: User = Depends(get_current_user)) -> UserProfileOut:
    return _profile_out(user)


@router.patch("/users/me", response_model=UserProfileOut)
def patch_my_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileOut:
    try:
        updated = UserService(db).update_profile(user.id, body)
    except UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found") from None
    return _profile_out(updated)


@router.post("/users/me/assert-login", response_model=UserProfileOut)
def assert_login(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileOut:
    try:
        ok = UserService(db).assert_can_login(user.email)
    except EmailNotVerified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Email not verified"
        ) from None
    except UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found") from None
    return _profile_out(ok)


# ── Orgs ─────────────────────────────────────────────────────────────────────


def _require_role(user: User, *allowed: str) -> None:
    if user.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient role")


@router.post("/orgs", status_code=status.HTTP_201_CREATED, response_model=OrgOut)
def create_org(
    body: OrgCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgOut:
    _require_role(user, "owner", "admin")
    try:
        org = OrgService(db).create(body)
    except OrgSlugTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Slug taken") from None
    return _org_out(org)


@router.patch("/orgs/{org_id}", response_model=OrgOut)
def update_org(
    org_id: _uuid.UUID,
    body: OrgUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgOut:
    _require_role(user, "owner", "admin")
    try:
        org = OrgService(db).update(org_id, body)
    except OrgNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Org not found") from None
    except OrgSlugTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Slug taken") from None
    return _org_out(org)


@router.get("/orgs/{org_id}", response_model=OrgOut)
def get_org(
    org_id: _uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgOut:
    try:
        org = OrgService(db).get(org_id)
    except OrgNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Org not found") from None
    return _org_out(org)


@router.post("/orgs/{org_id}/restore", response_model=OrgOut)
def restore_org(
    org_id: _uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgOut:
    """Restore a soft-deleted org if within the 30-day recovery window.

    Returns:
        200 + org payload — restoration succeeded.
        404 — org id unknown.
        409 — org is not archived (nothing to restore).
        410 Gone — archived more than 30 days ago, retention window closed.
    """
    _require_role(user, "owner", "admin")
    try:
        org = OrgService(db).restore(org_id)
    except OrgNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Org not found") from None
    except OrgNotArchived:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Org is not archived"
        ) from None
    except OrgRestoreWindowExpired:
        raise HTTPException(
            status.HTTP_410_GONE,
            detail="Org restore window (30 days) has expired",
        ) from None
    return _org_out(org)


# ── Invitations ──────────────────────────────────────────────────────────────


@router.post(
    "/orgs/{org_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=OrgInviteOut,
)
def create_invite(
    org_id: _uuid.UUID,
    body: OrgInviteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgInviteOut:
    _require_role(user, "owner", "admin")
    inv = OrgService(db).invite(org_id, email=body.email, role=body.role, by=user.id)
    return _invite_out(inv)


@router.get("/orgs/{org_id}/invitations", response_model=list[OrgInviteOut])
def list_invites(
    org_id: _uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrgInviteOut]:
    _require_role(user, "owner", "admin")
    invites = OrgService(db).list_pending_invites(org_id)
    return [_invite_out(i) for i in invites]


@router.delete(
    "/orgs/{org_id}/invitations/{invite_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_invite(
    org_id: _uuid.UUID,
    invite_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_role(user, "owner", "admin")
    try:
        OrgService(db).revoke_invite(invite_id)
    except InviteNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Invite not found"
        ) from None


@router.post(
    "/orgs/{org_id}/invitations/accept",
    response_model=OrgMemberOut,
)
def accept_invite(
    org_id: _uuid.UUID,
    token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgMemberOut:
    try:
        member = OrgService(db).accept_invitation(token, user)
    except InviteNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Invite not found"
        ) from None
    except InviteExpired:
        raise HTTPException(status.HTTP_410_GONE, detail="Invite expired") from None
    if member.org_id != org_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Token does not match this org"
        )
    return _member_out(member)


# ── Members ──────────────────────────────────────────────────────────────────


@router.get("/orgs/{org_id}/members", response_model=list[OrgMemberOut])
def list_members(
    org_id: _uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrgMemberOut]:
    _require_role(user, "owner", "admin")
    members = OrgService(db).list_members(org_id)
    return [_member_out(m) for m in members]


@router.delete(
    "/orgs/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    org_id: _uuid.UUID,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_role(user, "owner", "admin")
    if user.id == user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Cannot remove yourself"
        )
    try:
        OrgService(db).remove_member(org_id, user_id)
    except NotAMember:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not a member") from None
