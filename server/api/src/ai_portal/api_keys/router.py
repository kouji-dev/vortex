"""API key routes — /v1/api-keys/*

Endpoints (org-scoped, ``api-keys:*`` permissions required):

- GET    /v1/api-keys                  — list keys for the caller's org
- POST   /v1/api-keys                  — mint a new key (returns plaintext once)
- DELETE /v1/api-keys/{id}             — revoke (soft-delete) a key
- POST   /v1/api-keys/{id}/rotate      — mint a replacement + revoke the old
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.api_keys.model import ApiKey
from ai_portal.api_keys.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiKeyRotated,
)
from ai_portal.api_keys.service import (
    ApiKeyNotFound,
    ApiKeyService,
    CreatedApiKey,
)
from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_permission
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


def _to_out(key: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id,
        org_id=key.org_id,
        actor_user_id=key.actor_user_id,
        name=key.name,
        prefix=key.prefix,
        scopes_json=list(key.scopes_json or []),
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        created_at=key.created_at,
    )


def _to_created(created: CreatedApiKey) -> ApiKeyCreated:
    base = _to_out(created.key)
    return ApiKeyCreated(**base.model_dump(by_alias=False), plaintext=created.plaintext)


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    actor: Actor = Depends(require_permission("api-keys:read")),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    svc = ApiKeyService(db)
    return [_to_out(k) for k in svc.list_for_org(actor.org_id)]


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(
    body: ApiKeyCreate,
    actor: Actor = Depends(require_permission("api-keys:create")),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    svc = ApiKeyService(db)
    created = svc.create(
        org_id=actor.org_id,
        name=body.name,
        scopes=list(body.scopes or []),
        actor_user_id=body.actor_user_id,
        expires_at=body.expires_at,
    )
    return _to_created(created)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("api-keys:revoke")),
    db: Session = Depends(get_db),
) -> None:
    try:
        ApiKeyService(db).revoke(org_id=actor.org_id, key_id=key_id)
    except ApiKeyNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="api key not found") from e


@router.post("/{key_id}/rotate", response_model=ApiKeyRotated)
def rotate_api_key(
    key_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("api-keys:create")),
    db: Session = Depends(get_db),
) -> ApiKeyRotated:
    try:
        new_created, revoked_id = ApiKeyService(db).rotate(
            org_id=actor.org_id, key_id=key_id
        )
    except ApiKeyNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="api key not found") from e
    return ApiKeyRotated(new_key=_to_created(new_created), revoked_id=revoked_id)
