"""Org lifecycle + membership service.

Thin orchestrator over :class:`OrgRepo`. Covers:

- create / update / list orgs
- invite / accept / revoke / list invites
- add_member / remove_member / is_member / list_members

Invitation token is a URL-safe random 32-byte string. We persist the raw token
in :class:`OrgInvite.token` (unique) because legacy callers already do; future
work hardens this to ``token_hash`` everywhere.
"""
from __future__ import annotations

import secrets
import uuid as _uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.model import Org, OrgInvite, OrgMember, User
from ai_portal.auth.orgs_repository import OrgRepo
from ai_portal.auth.orgs_schemas import OrgCreate, OrgInviteCreate, OrgUpdate

INVITE_EXPIRY_DAYS = 7
ORG_RESTORE_WINDOW_DAYS = 30


class OrgSlugTaken(Exception):
    """Raised when attempting to create or rename an org to a slug already in use."""


class OrgNotFound(Exception):
    """Raised when an org id/slug lookup misses."""


class OrgNotArchived(Exception):
    """Raised when restoring an org that is not currently archived."""


class OrgRestoreWindowExpired(Exception):
    """Raised when attempting to restore an org archived more than 30 days ago."""


class InviteNotFound(Exception):
    """Raised on accept_invitation with an unknown / consumed / revoked token."""


class InviteExpired(Exception):
    """Raised on accept_invitation when the invite has expired."""


class NotAMember(Exception):
    """Raised on remove_member when target is not currently a member."""


class OrgService:
    """Org + invitation + membership orchestrator.

    All mutating methods ``commit`` the session — callers do not need to.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = OrgRepo(db)

    # ── org lifecycle ────────────────────────────────────────────────────────

    def create(self, dto: OrgCreate) -> Org:
        if self.repo.by_slug(dto.slug):
            raise OrgSlugTaken(dto.slug)
        org = Org(
            slug=dto.slug,
            name=dto.name,
            region=dto.region,
            status="active",
        )
        self.repo.add(org)
        self.db.commit()
        self.db.refresh(org)
        return org

    def update(self, org_id: _uuid.UUID, dto: OrgUpdate) -> Org:
        org = self.repo.by_id(org_id)
        if org is None:
            raise OrgNotFound(str(org_id))
        if dto.slug is not None and dto.slug != org.slug:
            existing = self.repo.by_slug(dto.slug)
            if existing and existing.id != org_id:
                raise OrgSlugTaken(dto.slug)
            org.slug = dto.slug
        if dto.name is not None:
            org.name = dto.name
        if dto.region is not None:
            org.region = dto.region
        self.db.commit()
        self.db.refresh(org)
        return org

    def get(self, org_id: _uuid.UUID) -> Org:
        org = self.repo.by_id(org_id)
        if org is None:
            raise OrgNotFound(str(org_id))
        return org

    def archive(self, org_id: _uuid.UUID) -> Org:
        """Soft-delete an org by stamping ``archived_at`` to now."""
        org = self.repo.by_id(org_id)
        if org is None:
            raise OrgNotFound(str(org_id))
        if org.archived_at is None:
            org.archived_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(org)
        return org

    def restore(self, org_id: _uuid.UUID) -> Org:
        """Restore a soft-deleted org if within the 30-day recovery window.

        Raises:
            OrgNotFound: org id does not exist.
            OrgNotArchived: org is not currently archived.
            OrgRestoreWindowExpired: archived_at is older than ``ORG_RESTORE_WINDOW_DAYS``.
        """
        org = self.repo.by_id(org_id)
        if org is None:
            raise OrgNotFound(str(org_id))
        if org.archived_at is None:
            raise OrgNotArchived(str(org_id))
        archived_at = org.archived_at
        if archived_at.tzinfo is None:
            archived_at = archived_at.replace(tzinfo=UTC)
        cutoff = datetime.now(UTC) - timedelta(days=ORG_RESTORE_WINDOW_DAYS)
        if archived_at < cutoff:
            raise OrgRestoreWindowExpired(str(org_id))
        org.archived_at = None
        self.db.commit()
        self.db.refresh(org)
        return org

    # ── invitations ──────────────────────────────────────────────────────────

    def invite(
        self,
        org_id: _uuid.UUID,
        email: str,
        role: str = "member",
        by: int | None = None,
    ) -> OrgInvite:
        """Create a pending invite. Revokes any prior pending invite for the same email."""
        norm_email = email.strip().lower()
        # Revoke prior pending invite for the same email in this org.
        prior = self.db.scalars(
            select(OrgInvite).where(
                OrgInvite.org_id == org_id,
                OrgInvite.invited_email == norm_email,
                OrgInvite.accepted_at.is_(None),
                OrgInvite.revoked_at.is_(None),
            )
        ).first()
        if prior is not None:
            prior.revoked_at = datetime.now(UTC)
            self.db.flush()

        invite = OrgInvite(
            org_id=org_id,
            invited_email=norm_email,
            token=secrets.token_urlsafe(32),
            role=role,
            created_by_user_id=by if by is not None else 0,
            expires_at=datetime.now(UTC) + timedelta(days=INVITE_EXPIRY_DAYS),
        )
        self.db.add(invite)
        self.db.commit()
        self.db.refresh(invite)
        return invite

    def get_invite_by_token(self, token: str) -> OrgInvite:
        invite = self.db.scalars(
            select(OrgInvite).where(
                OrgInvite.token == token,
                OrgInvite.accepted_at.is_(None),
                OrgInvite.revoked_at.is_(None),
            )
        ).first()
        if invite is None:
            raise InviteNotFound(token)
        expires_at = invite.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise InviteExpired(token)
        return invite

    def accept_invitation(self, token: str, user: User) -> OrgMember:
        """Mark invite accepted, attach the user as a member, return the membership."""
        invite = self.get_invite_by_token(token)
        if invite.invited_email != (user.email or "").strip().lower():
            # The orchestrator can decide whether to reject or migrate; default reject.
            raise InviteNotFound(token)
        member = self.add_member(invite.org_id, user.id, role=invite.role)
        invite.accepted_at = datetime.now(UTC)
        # Backwards-compat: keep users.org_id pointing at their primary org.
        if user.org_id is None:
            user.org_id = invite.org_id
        if user.role in (None, "member"):
            user.role = invite.role
        self.db.commit()
        self.db.refresh(member)
        return member

    def revoke_invite(self, invite_id: int) -> None:
        invite = self.db.get(OrgInvite, invite_id)
        if invite is None:
            raise InviteNotFound(str(invite_id))
        invite.revoked_at = datetime.now(UTC)
        self.db.commit()

    def list_pending_invites(self, org_id: _uuid.UUID) -> list[OrgInvite]:
        rows = self.db.scalars(
            select(OrgInvite).where(
                OrgInvite.org_id == org_id,
                OrgInvite.accepted_at.is_(None),
                OrgInvite.revoked_at.is_(None),
                OrgInvite.expires_at > datetime.now(UTC),
            )
        ).all()
        return list(rows)

    # ── memberships ──────────────────────────────────────────────────────────

    def add_member(
        self, org_id: _uuid.UUID, user_id: int, role: str = "member"
    ) -> OrgMember:
        existing = self.db.scalars(
            select(OrgMember).where(
                OrgMember.org_id == org_id, OrgMember.user_id == user_id
            )
        ).first()
        if existing is not None:
            existing.role = role
            existing.removed_at = None
            self.db.flush()
            return existing
        member = OrgMember(org_id=org_id, user_id=user_id, role=role)
        self.db.add(member)
        self.db.flush()
        return member

    def remove_member(self, org_id: _uuid.UUID, user_id: int) -> None:
        member = self.db.scalars(
            select(OrgMember).where(
                OrgMember.org_id == org_id,
                OrgMember.user_id == user_id,
                OrgMember.removed_at.is_(None),
            )
        ).first()
        if member is None:
            raise NotAMember(f"user {user_id} not in org {org_id}")
        member.removed_at = datetime.now(UTC)
        self.db.commit()

    def is_member(self, org_id: _uuid.UUID, user_id: int) -> bool:
        member = self.db.scalars(
            select(OrgMember).where(
                OrgMember.org_id == org_id,
                OrgMember.user_id == user_id,
                OrgMember.removed_at.is_(None),
            )
        ).first()
        return member is not None

    def list_members(self, org_id: _uuid.UUID) -> list[OrgMember]:
        rows = self.db.scalars(
            select(OrgMember).where(
                OrgMember.org_id == org_id, OrgMember.removed_at.is_(None)
            )
        ).all()
        return list(rows)
