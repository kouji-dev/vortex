"""TeamService — thin orchestrator over :class:`TeamRepo`.

CRUD for teams, membership management, and the two derived aggregations the
spec calls for:

- per-team API-key count (keys stay owned by individuals)
- per-team usage (sum of ``usage_rollup`` across the team's members)

Business rules live here; raw SQL lives in the repository.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.auth.model import User
from ai_portal.control_plane.teams.model import Team, TeamMember
from ai_portal.control_plane.teams.repository import TeamRepo
from ai_portal.usage.model import UsageRollup


class TeamNotFound(Exception):
    """Raised when a team id is not present in the caller's org."""


class TeamSlugTaken(Exception):
    """Raised when a slug collides with an existing team in the org."""


class TeamMemberNotFound(Exception):
    """Raised when a (team, user) membership row is absent."""


class UserNotInOrg(Exception):
    """Raised when adding a user that does not belong to the team's org."""


class TeamService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = TeamRepo(db)

    # ── teams ────────────────────────────────────────────────────────────
    def create(
        self,
        *,
        org_id: _uuid.UUID,
        slug: str,
        name: str,
        description: str | None = None,
    ) -> Team:
        if self.repo.by_slug(org_id=org_id, slug=slug) is not None:
            raise TeamSlugTaken(slug)
        team = Team(org_id=org_id, slug=slug, name=name, description=description)
        self.repo.add(team)
        self.db.commit()
        self.db.refresh(team)
        return team

    def get(self, *, org_id: _uuid.UUID, team_id: _uuid.UUID) -> Team:
        team = self.repo.by_id(org_id=org_id, team_id=team_id)
        if team is None:
            raise TeamNotFound(str(team_id))
        return team

    def list_for_org(
        self, org_id: _uuid.UUID, *, include_archived: bool = False
    ) -> Sequence[Team]:
        return self.repo.list_for_org(org_id, include_archived=include_archived)

    def update(
        self,
        *,
        org_id: _uuid.UUID,
        team_id: _uuid.UUID,
        slug: str | None = None,
        name: str | None = None,
        description: str | None = None,
        archived: bool | None = None,
    ) -> Team:
        team = self.get(org_id=org_id, team_id=team_id)
        if slug is not None and slug != team.slug:
            if self.repo.by_slug(org_id=org_id, slug=slug) is not None:
                raise TeamSlugTaken(slug)
            team.slug = slug
        if name is not None:
            team.name = name
        if description is not None:
            team.description = description
        if archived is not None:
            team.archived_at = datetime.now(tz=team.created_at.tzinfo) if archived else None
        self.db.commit()
        self.db.refresh(team)
        return team

    def delete(self, *, org_id: _uuid.UUID, team_id: _uuid.UUID) -> None:
        team = self.get(org_id=org_id, team_id=team_id)
        self.repo.delete(team)
        self.db.commit()

    def member_count(self, team_id: _uuid.UUID) -> int:
        return self.repo.member_count(team_id)

    def member_counts_for_org(self, org_id: _uuid.UUID) -> dict[_uuid.UUID, int]:
        return self.repo.member_counts_for_org(org_id)

    # ── members ──────────────────────────────────────────────────────────
    def add_member(
        self,
        *,
        org_id: _uuid.UUID,
        team_id: _uuid.UUID,
        user_id: int,
        role: str | None = None,
    ) -> TeamMember:
        team = self.get(org_id=org_id, team_id=team_id)
        # Guard: only org members may join an org's team.
        user = self.db.get(User, user_id)
        if user is None or user.org_id != org_id:
            raise UserNotInOrg(str(user_id))
        existing = self.repo.member(team_id=team.id, user_id=user_id)
        if existing is not None:
            # Idempotent: update the role on re-add.
            existing.role = role
            self.db.commit()
            self.db.refresh(existing)
            return existing
        member = TeamMember(
            team_id=team.id, org_id=org_id, user_id=user_id, role=role
        )
        self.repo.add_member(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def list_members(
        self, *, org_id: _uuid.UUID, team_id: _uuid.UUID
    ) -> Sequence[tuple[TeamMember, User | None]]:
        self.get(org_id=org_id, team_id=team_id)  # 404 if not in org
        return self.repo.list_members(team_id)

    def set_member_role(
        self,
        *,
        org_id: _uuid.UUID,
        team_id: _uuid.UUID,
        user_id: int,
        role: str | None,
    ) -> TeamMember:
        self.get(org_id=org_id, team_id=team_id)
        member = self.repo.member(team_id=team_id, user_id=user_id)
        if member is None:
            raise TeamMemberNotFound(str(user_id))
        member.role = role
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(
        self, *, org_id: _uuid.UUID, team_id: _uuid.UUID, user_id: int
    ) -> None:
        """Drop the team attribution. Personal keys are untouched."""
        self.get(org_id=org_id, team_id=team_id)
        member = self.repo.member(team_id=team_id, user_id=user_id)
        if member is None:
            raise TeamMemberNotFound(str(user_id))
        self.repo.remove_member(member)
        self.db.commit()

    # ── aggregations ─────────────────────────────────────────────────────
    def key_count(self, *, org_id: _uuid.UUID, team_id: _uuid.UUID) -> int:
        self.get(org_id=org_id, team_id=team_id)
        return self.repo.key_count(team_id)

    def usage(
        self,
        *,
        org_id: _uuid.UUID,
        team_id: _uuid.UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> dict:
        """Sum ``usage_rollup`` across the team's members.

        Keys stay user-owned; usage is rolled up per user, so a team total is
        the sum over the team's member ``user_id`` set.
        """
        self.get(org_id=org_id, team_id=team_id)
        user_ids = self.repo.member_user_ids(team_id)
        zero = {
            "team_id": team_id,
            "member_count": len(user_ids),
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "cost_usd": 0.0,
            "message_count": 0,
        }
        if not user_ids:
            return zero
        q = select(
            func.coalesce(func.sum(UsageRollup.input_tokens), 0),
            func.coalesce(func.sum(UsageRollup.output_tokens), 0),
            func.coalesce(func.sum(UsageRollup.cached_input_tokens), 0),
            func.coalesce(func.sum(UsageRollup.cost_usd), Decimal("0")),
            func.coalesce(func.sum(UsageRollup.message_count), 0),
        ).where(
            UsageRollup.org_id == org_id,
            UsageRollup.user_id.in_(user_ids),
        )
        if period_start is not None:
            q = q.where(UsageRollup.period_start >= period_start)
        if period_end is not None:
            q = q.where(UsageRollup.period_start < period_end)
        row = self.db.execute(q).one()
        return {
            "team_id": team_id,
            "member_count": len(user_ids),
            "input_tokens": int(row[0]),
            "output_tokens": int(row[1]),
            "cached_input_tokens": int(row[2]),
            "cost_usd": float(row[3]),
            "message_count": int(row[4]),
        }


def get_actor_teams(db: Session, *, org_id: _uuid.UUID, user_id: int) -> Sequence[Team]:
    """Internal contract — teams a user belongs to within an org.

    Backs ``get_actor_teams(actor)`` from the module-boundary surface.
    """
    return list(
        db.scalars(
            select(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                Team.org_id == org_id,
                TeamMember.user_id == user_id,
                Team.archived_at.is_(None),
            )
            .order_by(Team.created_at.asc())
        )
    )
