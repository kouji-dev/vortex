"""Repository — DB primitives for :class:`Team` / :class:`TeamMember`.

The service owns business rules; the repository is a thin query layer keyed by
org + team + user. Aggregations (key counts, usage) live here because they are
pure SQL over the membership join.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.api_keys.model import ApiKey
from ai_portal.auth.model import User
from ai_portal.control_plane.teams.model import Team, TeamMember


class TeamRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    # ── teams ────────────────────────────────────────────────────────────
    def add(self, team: Team) -> Team:
        self.s.add(team)
        self.s.flush()
        return team

    def by_id(self, *, org_id: _uuid.UUID, team_id: _uuid.UUID) -> Team | None:
        return self.s.scalars(
            select(Team).where(Team.id == team_id, Team.org_id == org_id)
        ).first()

    def by_slug(self, *, org_id: _uuid.UUID, slug: str) -> Team | None:
        return self.s.scalars(
            select(Team).where(Team.org_id == org_id, Team.slug == slug)
        ).first()

    def list_for_org(
        self, org_id: _uuid.UUID, *, include_archived: bool = False
    ) -> Sequence[Team]:
        q = select(Team).where(Team.org_id == org_id)
        if not include_archived:
            q = q.where(Team.archived_at.is_(None))
        return list(self.s.scalars(q.order_by(Team.created_at.asc())))

    def delete(self, team: Team) -> None:
        self.s.delete(team)
        self.s.flush()

    # ── members ──────────────────────────────────────────────────────────
    def add_member(self, member: TeamMember) -> TeamMember:
        self.s.add(member)
        self.s.flush()
        return member

    def member(
        self, *, team_id: _uuid.UUID, user_id: int
    ) -> TeamMember | None:
        return self.s.scalars(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == user_id
            )
        ).first()

    def list_members(self, team_id: _uuid.UUID) -> Sequence[tuple[TeamMember, User | None]]:
        rows = self.s.execute(
            select(TeamMember, User)
            .outerjoin(User, User.id == TeamMember.user_id)
            .where(TeamMember.team_id == team_id)
            .order_by(TeamMember.created_at.asc())
        ).all()
        return [(tm, u) for tm, u in rows]

    def member_user_ids(self, team_id: _uuid.UUID) -> list[int]:
        return list(
            self.s.scalars(
                select(TeamMember.user_id).where(TeamMember.team_id == team_id)
            )
        )

    def remove_member(self, member: TeamMember) -> None:
        self.s.delete(member)
        self.s.flush()

    def member_count(self, team_id: _uuid.UUID) -> int:
        return int(
            self.s.scalar(
                select(func.count())
                .select_from(TeamMember)
                .where(TeamMember.team_id == team_id)
            )
            or 0
        )

    def member_counts_for_org(self, org_id: _uuid.UUID) -> dict[_uuid.UUID, int]:
        rows = self.s.execute(
            select(TeamMember.team_id, func.count())
            .where(TeamMember.org_id == org_id)
            .group_by(TeamMember.team_id)
        ).all()
        return {tid: int(c) for tid, c in rows}

    # ── aggregations (keys stay user-owned; team is a derived grouping) ──
    def key_count(self, team_id: _uuid.UUID) -> int:
        """Count live API keys owned by the team's members.

        Keys are matched via ``api_keys.actor_user_id`` joined to the team's
        membership. Revoked keys are excluded.
        """
        return int(
            self.s.scalar(
                select(func.count())
                .select_from(ApiKey)
                .join(TeamMember, TeamMember.user_id == ApiKey.actor_user_id)
                .where(
                    TeamMember.team_id == team_id,
                    ApiKey.revoked_at.is_(None),
                )
            )
            or 0
        )
