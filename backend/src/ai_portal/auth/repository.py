from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models.org import Org
from ai_portal.models.org_invite import OrgInvite
from ai_portal.models.user import User


def get_user_by_uuid(db: Session, user_uuid) -> User | None:
    return db.scalars(select(User).where(User.uuid == user_uuid)).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).first()


def get_pending_invite_by_token(db: Session, token: str) -> OrgInvite | None:
    return db.scalars(
        select(OrgInvite).where(
            OrgInvite.token == token,
            OrgInvite.accepted_at == None,  # noqa: E711
            OrgInvite.revoked_at == None,  # noqa: E711
        )
    ).first()


def get_personal_org_for_user(db: Session, user: User) -> Org | None:
    return db.scalars(
        select(Org).where(
            Org.id == user.org_id,
            Org.instance_mode == False,  # noqa: E712
        )
    ).first()


def accept_invite_and_commit(db: Session, invite: OrgInvite, user: User) -> None:
    invite.accepted_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
