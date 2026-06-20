"""Members facade — /v1/members/*

Actor-org-scoped (org derived from the caller), the sibling of /v1/teams that the
admin "Members" UI expects (apps/frontend admin-api.ts: fetchMembers /
inviteMember / fetchInvitations / updateMemberRole / removeMember /
revokeInvitation). Response shapes match admin-types.ts ``OrgMember`` /
``OrgInvitation``.

Backed by the same ``User.org_id`` membership model + ``OrgInvite`` table as the
legacy ``/api/orgs/me/*`` router (auth/routes_orgs.py) — this just re-exposes it
under the versioned, current-org path the frontend was built against.
"""
from __future__ import annotations

import secrets
import uuid as _uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.auth.model import OrgInvite, User

router = APIRouter(prefix="/v1/members", tags=["members"])

INVITE_EXPIRY_DAYS = 7
_ROLE = r"^(owner|admin|member|viewer)$"


# ── Schemas (match admin-types.ts OrgMember / OrgInvitation) ────────────────


class MemberOut(BaseModel):
    user_id: str
    email: str
    name: str | None = None
    role: str
    joined_at: datetime
    last_active_at: datetime | None = None


class InvitationOut(BaseModel):
    id: str
    email: str
    role: str
    invited_by: str
    expires_at: datetime
    created_at: datetime


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="member", pattern=_ROLE)


class RolePatch(BaseModel):
    role: str = Field(pattern=_ROLE)


# ── helpers ─────────────────────────────────────────────────────────────────


def _require_role(user: User, *allowed: str) -> None:
    if user.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient role")


def _member_out(u: User) -> MemberOut:
    return MemberOut(
        user_id=str(u.id),
        email=u.email,
        name=u.name,
        role=u.role,
        joined_at=u.created_at,
        last_active_at=None,
    )


def _invite_out(inv: OrgInvite) -> InvitationOut:
    return InvitationOut(
        id=str(inv.id),
        email=inv.invited_email,
        role=inv.role,
        invited_by=str(inv.created_by_user_id),
        expires_at=inv.expires_at,
        created_at=inv.created_at,
    )


# ── invitations (declared before /{user_id} so the static segment wins) ─────


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InvitationOut]:
    _require_role(user, "owner", "admin")
    invites = db.scalars(
        select(OrgInvite).where(
            OrgInvite.org_id == org_id,
            OrgInvite.accepted_at.is_(None),
            OrgInvite.revoked_at.is_(None),
            OrgInvite.expires_at > datetime.now(UTC),
        )
    ).all()
    return [_invite_out(i) for i in invites]


@router.post(
    "/invitations", status_code=status.HTTP_201_CREATED, response_model=InvitationOut
)
def create_invitation(
    body: InviteCreate,
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvitationOut:
    _require_role(user, "owner", "admin")
    email = body.email.lower().strip()
    # Revoke any prior pending invite for the same email in this org.
    existing = db.scalars(
        select(OrgInvite).where(
            OrgInvite.org_id == org_id,
            OrgInvite.invited_email == email,
            OrgInvite.accepted_at.is_(None),
            OrgInvite.revoked_at.is_(None),
        )
    ).first()
    if existing:
        existing.revoked_at = datetime.now(UTC)
        db.flush()
    invite = OrgInvite(
        org_id=org_id,
        invited_email=email,
        token=secrets.token_urlsafe(32),
        role=body.role,
        created_by_user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return _invite_out(invite)


@router.delete("/invitations/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invite_id: int,
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_role(user, "owner", "admin")
    invite = db.scalars(
        select(OrgInvite).where(
            OrgInvite.id == invite_id, OrgInvite.org_id == org_id
        )
    ).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found")
    invite.revoked_at = datetime.now(UTC)
    db.commit()


# ── members ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[MemberOut])
def list_members(
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    _require_role(user, "owner", "admin")
    members = db.scalars(select(User).where(User.org_id == org_id)).all()
    return [_member_out(m) for m in members]


@router.patch("/{user_id}", response_model=MemberOut)
def update_member_role(
    user_id: int,
    body: RolePatch,
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberOut:
    _require_role(user, "owner")
    member = db.scalars(
        select(User).where(User.id == user_id, User.org_id == org_id)
    ).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.id == user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Cannot change your own role"
        )
    member.role = body.role
    db.commit()
    db.refresh(member)
    return _member_out(member)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: int,
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_role(user, "owner", "admin")
    member = db.scalars(
        select(User).where(User.id == user_id, User.org_id == org_id)
    ).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.id == user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Cannot remove yourself"
        )
    member.org_id = None
    member.role = "member"
    db.commit()
