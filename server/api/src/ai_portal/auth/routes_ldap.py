"""LDAP/AD routes — public bind login + admin connection CRUD.

Public:
- POST /v1/auth/ldap/login  — username + password → directory bind → session

Admin (``idp:read`` / ``idp:write`` — directory is an identity surface):
- GET    /v1/ldap-connections
- POST   /v1/ldap-connections
- GET    /v1/ldap-connections/{id}
- PATCH  /v1/ldap-connections/{id}
- DELETE /v1/ldap-connections/{id}
- POST   /v1/ldap-connections/{id}/test
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import ai_portal.auth.directory.providers  # noqa: F401 — register providers
from ai_portal.auth.claims_provision import ProvisionError, provision_from_claims
from ai_portal.auth.deps import get_db
from ai_portal.auth.directory.providers.ldap import (
    DirectoryAuthError,
    DirectoryConnectionError,
)
from ai_portal.auth.directory.schemas import (
    LdapConnectionCreate,
    LdapConnectionOut,
    LdapConnectionPatch,
    LdapLoginRequest,
    LdapTestResult,
)
from ai_portal.auth.directory.service import (
    DirectoryService,
    LdapConnectionNotFound,
    resolve_connection_for_login,
)
from ai_portal.auth.limiter import login_limiter
from ai_portal.auth.schemas import TokenResponse
from ai_portal.auth.sessions import create_session
from ai_portal.auth.strategies.dev import UserManager
from ai_portal.control_plane.deps import require_permission
from ai_portal.core.config import get_settings
from ai_portal.rbac.service import Actor, RbacService

public_router = APIRouter(prefix="/v1/auth/ldap", tags=["auth", "ldap"])
admin_router = APIRouter(prefix="/v1/ldap-connections", tags=["ldap", "admin"])


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "-"


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


# ── group → role assignment ──────────────────────────────────────────────────


def _apply_group_roles(db: Session, user, roles: list[str]) -> None:
    """Assign mapped RBAC system roles to the user in their org.

    Idempotent best-effort: also sets ``user.role`` to the strongest mapped
    role so the denormalized column reflects directory groups. Unknown role
    names are skipped.
    """
    if not roles or user.org_id is None:
        return
    rank = {"owner": 4, "admin": 3, "member": 2, "viewer": 1, "service": 0}
    valid = [r for r in roles if r in rank]
    if not valid:
        return
    strongest = max(valid, key=lambda r: rank.get(r, 0))
    user.role = strongest
    rbac = RbacService(db)
    for role_name in valid:
        try:
            rbac.assign_system_role(
                user.org_id, role_name=role_name, user_id=user.id
            )
        except Exception:  # noqa: BLE001 — assignment is best-effort / may exist
            db.rollback()


# ── public: bind login ───────────────────────────────────────────────────────


@public_router.post("/login", response_model=TokenResponse)
def ldap_login(
    body: LdapLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ip = _client_ip(request)
    retry_after = login_limiter.check(ip, f"ldap:{body.username}")
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too_many_login_attempts",
            headers={"Retry-After": str(retry_after)},
        )

    conn = resolve_connection_for_login(
        db, connection_id=body.connection_id, org_slug=body.org_slug
    )
    if conn is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "ldap_connection_not_found"},
        )

    svc = DirectoryService(db)
    try:
        claims = svc.authenticate(
            conn, username=body.username, password=body.password
        )
    except DirectoryAuthError as exc:
        login_limiter.record_failure(ip, f"ldap:{body.username}")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials", "message": str(exc)},
        )
    except DirectoryConnectionError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={"error": "directory_unreachable", "message": str(exc)},
        )

    try:
        user = provision_from_claims(db, claims=claims, org_id=conn.org_id)
    except ProvisionError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "provision_failed", "message": str(exc)},
        )

    roles = list(claims.raw.get("roles") or []) if isinstance(claims.raw, dict) else []
    _apply_group_roles(db, user, roles)
    db.commit()
    login_limiter.record_success(ip, f"ldap:{body.username}")

    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    session_id = _uuid.uuid4()
    tokens = manager.create_tokens(user, session_id=session_id)
    create_session(
        db,
        user_id=user.id,
        session_id=session_id,
        refresh_token=tokens["refresh_token"],
        ip=ip,
        user_agent=_user_agent(request),
    )
    return TokenResponse(**tokens)


# ── admin: connection CRUD ───────────────────────────────────────────────────


@admin_router.get("", response_model=list[LdapConnectionOut])
def list_connections(
    actor: Actor = Depends(require_permission("idp:read")),
    db: Session = Depends(get_db),
) -> list[LdapConnectionOut]:
    rows = DirectoryService(db).list_for_org(actor.org_id)
    return [LdapConnectionOut.model_validate(r) for r in rows]


@admin_router.post(
    "", response_model=LdapConnectionOut, status_code=status.HTTP_201_CREATED
)
def create_connection(
    body: LdapConnectionCreate,
    actor: Actor = Depends(require_permission("idp:write")),
    db: Session = Depends(get_db),
) -> LdapConnectionOut:
    conn = DirectoryService(db).create(
        org_id=actor.org_id,
        name=body.name,
        kind=body.kind,
        host=body.host,
        port=body.port,
        bind_dn=body.bind_dn,
        bind_secret=body.bind_secret,
        base_dn=body.base_dn,
        user_filter=body.user_filter,
        group_filter=body.group_filter,
        tls_mode=body.tls_mode,
        attr_map=body.attr_map,
        group_role_map=body.group_role_map,
        enabled=body.enabled,
    )
    return LdapConnectionOut.model_validate(conn)


@admin_router.get("/{conn_id}", response_model=LdapConnectionOut)
def get_connection(
    conn_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("idp:read")),
    db: Session = Depends(get_db),
) -> LdapConnectionOut:
    try:
        conn = DirectoryService(db).get(org_id=actor.org_id, conn_id=conn_id)
    except LdapConnectionNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connection not found") from e
    return LdapConnectionOut.model_validate(conn)


@admin_router.patch("/{conn_id}", response_model=LdapConnectionOut)
def patch_connection(
    conn_id: _uuid.UUID,
    body: LdapConnectionPatch,
    actor: Actor = Depends(require_permission("idp:write")),
    db: Session = Depends(get_db),
) -> LdapConnectionOut:
    fields = body.model_dump(exclude_unset=True)
    try:
        conn = DirectoryService(db).update(
            org_id=actor.org_id, conn_id=conn_id, **fields
        )
    except LdapConnectionNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connection not found") from e
    return LdapConnectionOut.model_validate(conn)


@admin_router.delete("/{conn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    conn_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("idp:write")),
    db: Session = Depends(get_db),
) -> None:
    try:
        DirectoryService(db).delete(org_id=actor.org_id, conn_id=conn_id)
    except LdapConnectionNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connection not found") from e


@admin_router.post("/{conn_id}/test", response_model=LdapTestResult)
def test_connection(
    conn_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("idp:write")),
    db: Session = Depends(get_db),
) -> LdapTestResult:
    try:
        ok, msg = DirectoryService(db).test(org_id=actor.org_id, conn_id=conn_id)
    except LdapConnectionNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connection not found") from e
    return LdapTestResult(ok=ok, message=msg)
