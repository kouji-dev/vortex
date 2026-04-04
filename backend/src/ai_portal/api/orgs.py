from __future__ import annotations

import secrets
import uuid as _uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_current_org_id, get_current_user, get_db
from ai_portal.models.org import Org
from ai_portal.models.org_invite import OrgInvite
from ai_portal.models.user import User

router = APIRouter(prefix="/api/orgs", tags=["orgs"])

INVITE_EXPIRY_DAYS = 7


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrgRead(BaseModel):
    id: str
    slug: str
    name: str
    instance_mode: bool

    model_config = {"from_attributes": True}


class OrgPatch(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(default=None, max_length=64)


class MemberRead(BaseModel):
    id: int
    email: str
    role: str
    is_verified: bool

    model_config = {"from_attributes": True}


class MemberRolePatch(BaseModel):
    role: str = Field(pattern="^(owner|admin|member)$")


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="member", pattern="^(admin|member)$")


class InviteRead(BaseModel):
    id: int
    invited_email: str
    role: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_role(user: User, *allowed: str) -> None:
    if user.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient role")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/me", response_model=OrgRead)
def get_my_org(
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> OrgRead:
    org = db.scalars(select(Org).where(Org.id == org_id)).first()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Org not found")
    return OrgRead.model_validate(org)


@router.patch("/me", response_model=OrgRead)
def update_my_org(
    body: OrgPatch,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> OrgRead:
    _require_role(user, "owner", "admin")
    org = db.scalars(select(Org).where(Org.id == org_id)).first()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Org not found")
    if body.name is not None:
        org.name = body.name
    if body.slug is not None:
        existing = db.scalars(select(Org).where(Org.slug == body.slug, Org.id != org_id)).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Slug already taken")
        org.slug = body.slug
    db.commit()
    db.refresh(org)
    return OrgRead.model_validate(org)


@router.get("/me/members", response_model=list[MemberRead])
def list_members(
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MemberRead]:
    _require_role(user, "owner", "admin")
    members = db.scalars(select(User).where(User.org_id == org_id)).all()
    return [MemberRead.model_validate(m) for m in members]


@router.patch("/me/members/{member_id}", response_model=MemberRead)
def update_member_role(
    member_id: int,
    body: MemberRolePatch,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> MemberRead:
    _require_role(user, "owner")
    member = db.scalars(
        select(User).where(User.id == member_id, User.org_id == org_id)
    ).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot change your own role")
    member.role = body.role
    db.commit()
    db.refresh(member)
    return MemberRead.model_validate(member)


@router.delete("/me/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: int,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> None:
    _require_role(user, "owner", "admin")
    member = db.scalars(
        select(User).where(User.id == member_id, User.org_id == org_id)
    ).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot remove yourself")
    member.org_id = None
    member.role = "member"
    db.commit()


@router.post("/me/invites", status_code=status.HTTP_201_CREATED, response_model=InviteRead)
def create_invite(
    body: InviteCreate,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> InviteRead:
    _require_role(user, "owner", "admin")
    # Revoke any existing pending invite for this email in this org
    existing = db.scalars(
        select(OrgInvite).where(
            OrgInvite.org_id == org_id,
            OrgInvite.invited_email == body.email.lower().strip(),
            OrgInvite.accepted_at == None,  # noqa: E711
            OrgInvite.revoked_at == None,  # noqa: E711
        )
    ).first()
    if existing:
        existing.revoked_at = datetime.now(UTC)
        db.flush()

    invite = OrgInvite(
        org_id=org_id,
        invited_email=body.email.lower().strip(),
        token=secrets.token_urlsafe(32),
        role=body.role,
        created_by_user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return InviteRead.model_validate(invite)


@router.get("/me/invites", response_model=list[InviteRead])
def list_invites(
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InviteRead]:
    _require_role(user, "owner", "admin")
    invites = db.scalars(
        select(OrgInvite).where(
            OrgInvite.org_id == org_id,
            OrgInvite.accepted_at == None,  # noqa: E711
            OrgInvite.revoked_at == None,  # noqa: E711
            OrgInvite.expires_at > datetime.now(UTC),
        )
    ).all()
    return [InviteRead.model_validate(i) for i in invites]


@router.delete("/me/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: int,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> None:
    _require_role(user, "owner", "admin")
    invite = db.scalars(
        select(OrgInvite).where(OrgInvite.id == invite_id, OrgInvite.org_id == org_id)
    ).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found")
    invite.revoked_at = datetime.now(UTC)
    db.commit()
