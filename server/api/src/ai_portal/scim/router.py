"""SCIM 2.0 + admin routes.

Two routers exported:

- ``scim_router`` — mounted at ``/scim/v2``. Bearer-token authenticated per
  endpoint (the token resolves the org). Implements RFC 7644 Users + Groups.
- ``admin_router`` — mounted at ``/v1/scim``. Org-admin actions (mint endpoint
  token, list / revoke endpoints, set group->role mapping).
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_permission
from ai_portal.rbac.service import Actor
from ai_portal.scim.model import ScimEndpoint, ScimGroup
from ai_portal.scim.schemas import (
    ScimEndpointCreate,
    ScimEndpointCreated,
    ScimEndpointOut,
    ScimGroupOut,
    ScimGroupRoleMap,
)
from ai_portal.scim.service import (
    ScimEndpointDisabled,
    ScimEndpointService,
    ScimError,
    ScimNotFound,
    ScimProvisioner,
    ScimUnauthorized,
)

# ── admin router ─────────────────────────────────────────────────────────────

admin_router = APIRouter(prefix="/v1/scim", tags=["scim-admin"])


def _endpoint_out(e: ScimEndpoint) -> ScimEndpointOut:
    return ScimEndpointOut(
        id=e.id,
        org_id=e.org_id,
        name=e.name,
        preset=e.preset,
        enabled=e.enabled,
        last_sync_at=e.last_sync_at,
        created_at=e.created_at,
        revoked_at=e.revoked_at,
    )


@admin_router.get("/endpoints", response_model=list[ScimEndpointOut])
def list_endpoints(
    actor: Actor = Depends(require_permission("scim:read")),
    db: Session = Depends(get_db),
) -> list[ScimEndpointOut]:
    rows = ScimEndpointService(db).list_endpoints(actor.org_id)
    return [_endpoint_out(r) for r in rows]


@admin_router.post(
    "/endpoints",
    response_model=ScimEndpointCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_endpoint(
    body: ScimEndpointCreate,
    actor: Actor = Depends(require_permission("scim:write")),
    db: Session = Depends(get_db),
) -> ScimEndpointCreated:
    created = ScimEndpointService(db).create_endpoint(
        org_id=actor.org_id, name=body.name, preset=body.preset
    )
    base = _endpoint_out(created.endpoint)
    return ScimEndpointCreated(**base.model_dump(), token=created.token)


@admin_router.delete(
    "/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_endpoint(
    endpoint_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("scim:write")),
    db: Session = Depends(get_db),
) -> None:
    try:
        ScimEndpointService(db).revoke_endpoint(
            org_id=actor.org_id, endpoint_id=endpoint_id
        )
    except ScimNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@admin_router.post(
    "/endpoints/{endpoint_id}/group-roles",
    response_model=ScimGroupOut,
)
def upsert_group_role(
    endpoint_id: _uuid.UUID,
    body: ScimGroupRoleMap,
    actor: Actor = Depends(require_permission("scim:write")),
    db: Session = Depends(get_db),
) -> ScimGroupOut:
    row = ScimEndpointService(db).set_group_role(
        endpoint_id=endpoint_id,
        org_id=actor.org_id,
        display_name=body.display_name,
        role_name=body.role_name,
    )
    return ScimGroupOut(
        id=row.id,
        display_name=row.display_name,
        external_id=row.external_id,
        role_name=row.role_name,
    )


# ── SCIM 2.0 wire router ─────────────────────────────────────────────────────

scim_router = APIRouter(prefix="/scim/v2", tags=["scim"])


def _scim_error_response(message: str, http_status: int) -> dict[str, Any]:
    """RFC 7644 §3.12 Error response shape."""
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
        "detail": message,
        "status": str(http_status),
    }


def _user_to_scim(user: Any) -> dict[str, Any]:
    """Render a User row as a SCIM 2.0 ``User`` resource."""
    scim_id = user.scim_external_id or str(user.uuid)
    name_parts = (user.name or "").strip().split(" ", 1)
    given = name_parts[0] if name_parts and name_parts[0] else None
    family = name_parts[1] if len(name_parts) > 1 else None
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": scim_id,
        "externalId": user.scim_external_id,
        "userName": user.email,
        "active": bool(user.is_active),
        "name": {
            "formatted": user.name,
            "givenName": given,
            "familyName": family,
        },
        "emails": [{"value": user.email, "primary": True}],
        "meta": {
            "resourceType": "User",
            "created": (user.created_at.isoformat() if user.created_at else None),
        },
    }


def _group_to_scim(group: ScimGroup) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": str(group.id),
        "externalId": group.external_id,
        "displayName": group.display_name,
        "meta": {
            "resourceType": "Group",
            "created": (group.created_at.isoformat() if group.created_at else None),
        },
    }


def _list_response(resources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(resources),
        "Resources": resources,
        "startIndex": 1,
        "itemsPerPage": len(resources),
    }


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def require_scim_endpoint(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> ScimEndpoint:
    """Resolve the SCIM endpoint for the inbound bearer token."""
    token = _bearer(authorization)
    try:
        return ScimEndpointService(db).resolve_token(token)
    except (ScimUnauthorized, ScimEndpointDisabled) as e:
        raise HTTPException(e.status, detail=str(e)) from e


def _handle_scim_error(e: ScimError) -> HTTPException:
    return HTTPException(
        status_code=e.status, detail=_scim_error_response(str(e), e.status)
    )


# ── Users ────────────────────────────────────────────────────────────────────


@scim_router.get("/Users")
async def list_scim_users(
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    users = ScimProvisioner(db, endpoint).list_users()
    return _list_response([_user_to_scim(u) for u in users])


@scim_router.post("/Users", status_code=status.HTTP_201_CREATED)
async def create_scim_user(
    request: Request,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = await request.json()
    try:
        result = ScimProvisioner(db, endpoint).create_user(payload)
    except ScimError as e:
        raise _handle_scim_error(e) from e
    return _user_to_scim(result.user)


@scim_router.get("/Users/{scim_id}")
async def get_scim_user(
    scim_id: str,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        user = ScimProvisioner(db, endpoint).get_user_by_scim_id(scim_id)
    except ScimError as e:
        raise _handle_scim_error(e) from e
    return _user_to_scim(user)


@scim_router.put("/Users/{scim_id}")
async def replace_scim_user(
    scim_id: str,
    request: Request,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = await request.json()
    try:
        user = ScimProvisioner(db, endpoint).replace_user(scim_id, payload)
    except ScimError as e:
        raise _handle_scim_error(e) from e
    return _user_to_scim(user)


@scim_router.patch("/Users/{scim_id}")
async def patch_scim_user(
    scim_id: str,
    request: Request,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = await request.json()
    try:
        user = ScimProvisioner(db, endpoint).patch_user(scim_id, payload)
    except ScimError as e:
        raise _handle_scim_error(e) from e
    return _user_to_scim(user)


@scim_router.delete("/Users/{scim_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scim_user(
    scim_id: str,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> None:
    try:
        ScimProvisioner(db, endpoint).delete_user(scim_id)
    except ScimError as e:
        raise _handle_scim_error(e) from e


# ── Groups ───────────────────────────────────────────────────────────────────


@scim_router.get("/Groups")
async def list_scim_groups(
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    groups = ScimProvisioner(db, endpoint).list_groups()
    return _list_response([_group_to_scim(g) for g in groups])


@scim_router.post("/Groups", status_code=status.HTTP_201_CREATED)
async def create_scim_group(
    request: Request,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = await request.json()
    try:
        group = ScimProvisioner(db, endpoint).create_group(payload)
    except ScimError as e:
        raise _handle_scim_error(e) from e
    return _group_to_scim(group)


@scim_router.get("/Groups/{scim_id}")
async def get_scim_group(
    scim_id: str,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        group = ScimProvisioner(db, endpoint).get_group(scim_id)
    except ScimError as e:
        raise _handle_scim_error(e) from e
    return _group_to_scim(group)


@scim_router.put("/Groups/{scim_id}")
async def replace_scim_group(
    scim_id: str,
    request: Request,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = await request.json()
    try:
        group = ScimProvisioner(db, endpoint).replace_group(scim_id, payload)
    except ScimError as e:
        raise _handle_scim_error(e) from e
    return _group_to_scim(group)


@scim_router.patch("/Groups/{scim_id}")
async def patch_scim_group(
    scim_id: str,
    request: Request,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = await request.json()
    try:
        group = ScimProvisioner(db, endpoint).patch_group(scim_id, payload)
    except ScimError as e:
        raise _handle_scim_error(e) from e
    return _group_to_scim(group)


@scim_router.delete(
    "/Groups/{scim_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_scim_group(
    scim_id: str,
    endpoint: ScimEndpoint = Depends(require_scim_endpoint),
    db: Session = Depends(get_db),
) -> None:
    try:
        ScimProvisioner(db, endpoint).delete_group(scim_id)
    except ScimError as e:
        raise _handle_scim_error(e) from e
