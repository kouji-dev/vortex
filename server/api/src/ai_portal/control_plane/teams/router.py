"""Team routes — /v1/teams/*

Org-scoped (org derived from the actor, mirroring /v1/members + /v1/api-keys):

- GET    /v1/teams                       — list teams in the caller's org
- POST   /v1/teams                       — create a team
- GET    /v1/teams/{id}                  — read a team (+ member count)
- PATCH  /v1/teams/{id}                  — rename / archive / describe
- DELETE /v1/teams/{id}                  — delete a team
- GET    /v1/teams/{id}/members          — list members
- POST   /v1/teams/{id}/members          — add a member (team-scoped role)
- PATCH  /v1/teams/{id}/members/{uid}    — set a member's team role
- DELETE /v1/teams/{id}/members/{uid}    — remove a member (keys untouched)
- GET    /v1/teams/{id}/key-count        — live key count across members
- GET    /v1/teams/{id}/usage            — usage summed across members
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.auth.model import User
from ai_portal.control_plane.deps import require_permission
from ai_portal.control_plane.teams.model import Team, TeamMember
from ai_portal.control_plane.teams.schemas import (
    TeamCreate,
    TeamKeyCount,
    TeamMemberAdd,
    TeamMemberOut,
    TeamMemberPatch,
    TeamOut,
    TeamPatch,
    TeamUsage,
)
from ai_portal.control_plane.teams.service import (
    TeamMemberNotFound,
    TeamNotFound,
    TeamService,
    TeamSlugTaken,
    UserNotInOrg,
)
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1/teams", tags=["teams"])


def _to_out(team: Team, *, member_count: int = 0) -> TeamOut:
    return TeamOut(
        id=team.id,
        org_id=team.org_id,
        slug=team.slug,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        archived_at=team.archived_at,
        member_count=member_count,
    )


def _member_to_out(tm: TeamMember, user: User | None) -> TeamMemberOut:
    return TeamMemberOut(
        id=tm.id,
        team_id=tm.team_id,
        user_id=tm.user_id,
        email=user.email if user else None,
        name=user.name if user else None,
        role=tm.role,
        created_at=tm.created_at,
    )


# ── teams ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[TeamOut])
def list_teams(
    include_archived: bool = False,
    actor: Actor = Depends(require_permission("teams:read")),
    db: Session = Depends(get_db),
) -> list[TeamOut]:
    svc = TeamService(db)
    teams = svc.list_for_org(actor.org_id, include_archived=include_archived)
    counts = svc.member_counts_for_org(actor.org_id)
    return [_to_out(t, member_count=counts.get(t.id, 0)) for t in teams]


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(
    body: TeamCreate,
    actor: Actor = Depends(require_permission("teams:write")),
    db: Session = Depends(get_db),
) -> TeamOut:
    try:
        team = TeamService(db).create(
            org_id=actor.org_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
        )
    except TeamSlugTaken as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="team slug already in use") from e
    return _to_out(team, member_count=0)


@router.get("/{team_id}", response_model=TeamOut)
def get_team(
    team_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("teams:read")),
    db: Session = Depends(get_db),
) -> TeamOut:
    svc = TeamService(db)
    try:
        team = svc.get(org_id=actor.org_id, team_id=team_id)
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e
    return _to_out(team, member_count=svc.member_count(team_id))


@router.patch("/{team_id}", response_model=TeamOut)
def patch_team(
    team_id: _uuid.UUID,
    body: TeamPatch,
    actor: Actor = Depends(require_permission("teams:write")),
    db: Session = Depends(get_db),
) -> TeamOut:
    svc = TeamService(db)
    try:
        team = svc.update(
            org_id=actor.org_id,
            team_id=team_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
            archived=body.archived,
        )
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e
    except TeamSlugTaken as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="team slug already in use") from e
    return _to_out(team, member_count=svc.member_count(team_id))


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("teams:write")),
    db: Session = Depends(get_db),
) -> None:
    try:
        TeamService(db).delete(org_id=actor.org_id, team_id=team_id)
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e


# ── members ──────────────────────────────────────────────────────────────


@router.get("/{team_id}/members", response_model=list[TeamMemberOut])
def list_team_members(
    team_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("teams:read")),
    db: Session = Depends(get_db),
) -> list[TeamMemberOut]:
    try:
        rows = TeamService(db).list_members(org_id=actor.org_id, team_id=team_id)
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e
    return [_member_to_out(tm, u) for tm, u in rows]


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_team_member(
    team_id: _uuid.UUID,
    body: TeamMemberAdd,
    actor: Actor = Depends(require_permission("teams:write")),
    db: Session = Depends(get_db),
) -> TeamMemberOut:
    try:
        member = TeamService(db).add_member(
            org_id=actor.org_id,
            team_id=team_id,
            user_id=body.user_id,
            role=body.role,
        )
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e
    except UserNotInOrg as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="user is not a member of this org"
        ) from e
    user = db.get(User, member.user_id)
    return _member_to_out(member, user)


@router.patch("/{team_id}/members/{user_id}", response_model=TeamMemberOut)
def patch_team_member(
    team_id: _uuid.UUID,
    user_id: int,
    body: TeamMemberPatch,
    actor: Actor = Depends(require_permission("teams:write")),
    db: Session = Depends(get_db),
) -> TeamMemberOut:
    try:
        member = TeamService(db).set_member_role(
            org_id=actor.org_id, team_id=team_id, user_id=user_id, role=body.role
        )
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e
    except TeamMemberNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="member not found") from e
    user = db.get(User, member.user_id)
    return _member_to_out(member, user)


@router.delete(
    "/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_team_member(
    team_id: _uuid.UUID,
    user_id: int,
    actor: Actor = Depends(require_permission("teams:write")),
    db: Session = Depends(get_db),
) -> None:
    try:
        TeamService(db).remove_member(
            org_id=actor.org_id, team_id=team_id, user_id=user_id
        )
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e
    except TeamMemberNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="member not found") from e


# ── aggregations ──────────────────────────────────────────────────────────


@router.get("/{team_id}/key-count", response_model=TeamKeyCount)
def team_key_count(
    team_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("teams:read")),
    db: Session = Depends(get_db),
) -> TeamKeyCount:
    svc = TeamService(db)
    try:
        keys = svc.key_count(org_id=actor.org_id, team_id=team_id)
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e
    return TeamKeyCount(
        team_id=team_id,
        member_count=svc.member_count(team_id),
        key_count=keys,
    )


@router.get("/{team_id}/usage", response_model=TeamUsage)
def team_usage(
    team_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("teams:read")),
    db: Session = Depends(get_db),
) -> TeamUsage:
    try:
        agg = TeamService(db).usage(org_id=actor.org_id, team_id=team_id)
    except TeamNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found") from e
    return TeamUsage(**agg)
