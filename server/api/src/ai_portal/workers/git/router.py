"""Git-integrations HTTP API.

Routes (prefix ``/v1/workers/git-integrations``):

- ``POST   ""``                      — connect a GitHub integration
- ``GET    ""``                      — list integrations
- ``DELETE "/{integration_id}"``     — delete an integration
- ``GET    "/{integration_id}/repos"``  — list repos for an integration
- ``PATCH  "/{integration_id}/repos"``  — toggle enabled repos
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.workers.git import connection_service as svc
from ai_portal.workers.git.schemas import (
    GitIntegrationConnect,
    GitIntegrationOut,
    GitRepoOut,
    ReposToggle,
)

router = APIRouter(prefix="/v1/workers/git-integrations", tags=["workers-git"])


# ── helpers ──────────────────────────────────────────────────────


def _uuid_or_422(raw: str, label: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(raw)
    except (ValueError, TypeError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"invalid {label}"
        )


def _integration_out(integration, db: Session) -> GitIntegrationOut:
    repos = svc.list_repos(db, integration.id)
    return GitIntegrationOut.from_orm_row(integration, repos)


# ── endpoints ────────────────────────────────────────────────────


@router.post(
    "",
    response_model=GitIntegrationOut,
    status_code=status.HTTP_201_CREATED,
)
async def connect_integration(
    body: GitIntegrationConnect,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> GitIntegrationOut:
    owner_user_id = user.uuid if body.scope == "user" else None
    scoped_org_id = org_id if body.scope == "org" else None
    try:
        integration = await svc.connect_github(
            db,
            owner_user_id=owner_user_id,
            org_id=scoped_org_id,
            token=body.token,
        )
    except svc.InvalidGitToken as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _integration_out(integration, db)


@router.get("", response_model=list[GitIntegrationOut])
def list_integrations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[GitIntegrationOut]:
    integrations = svc.list_integrations(
        db, owner_user_id=user.uuid, org_id=org_id
    )
    return [_integration_out(i, db) for i in integrations]


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> None:
    iid = _uuid_or_422(integration_id, "integration_id")
    svc.delete_integration(db, iid)
    db.commit()


@router.get(
    "/{integration_id}/repos",
    response_model=list[GitRepoOut],
)
def list_repos(
    integration_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[GitRepoOut]:
    iid = _uuid_or_422(integration_id, "integration_id")
    repos = svc.list_repos(db, iid)
    return [GitRepoOut.from_orm_row(r) for r in repos]


@router.patch(
    "/{integration_id}/repos",
    response_model=list[GitRepoOut],
)
def set_enabled_repos(
    integration_id: str,
    body: ReposToggle,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[GitRepoOut]:
    iid = _uuid_or_422(integration_id, "integration_id")
    repos = svc.set_enabled_repos(db, iid, set(body.enabled_full_names))
    db.commit()
    return [GitRepoOut.from_orm_row(r) for r in repos]
