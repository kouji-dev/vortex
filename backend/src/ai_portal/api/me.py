from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_app_roles, get_current_user, get_db
from ai_portal.api.rbac import require_app_roles
from ai_portal.config import get_settings
from ai_portal.models import User
from ai_portal.services import portal_api_keys as portal_keys_svc

router = APIRouter(prefix="/api", tags=["me"])


class MeRead(BaseModel):
    id: int
    email: str
    roles: list[str]
    display_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    preferred_username: str | None = None


@router.get("/me", response_model=MeRead)
def read_me(
    request: Request,
    user: User = Depends(get_current_user),
) -> MeRead:
    profile = getattr(request.state, "me_profile", None) or {}
    return MeRead(
        id=user.id,
        email=user.email,
        roles=get_app_roles(request),
        display_name=profile.get("display_name"),
        given_name=profile.get("given_name"),
        family_name=profile.get("family_name"),
        preferred_username=profile.get("preferred_username"),
    )


@router.get("/admin/ping")
def admin_ping(
    _: None = Depends(require_app_roles("Admin")),
) -> dict[str, str]:
    """RBAC probe: requires Entra app role Admin when auth_mode=entra (dev bypasses)."""
    return {"status": "ok"}


class PortalApiKeyCreate(BaseModel):
    label: str | None = Field(default=None, max_length=128)


class PortalApiKeyCreated(BaseModel):
    id: int
    token: str = Field(description="Shown once; store securely.")
    key_prefix: str
    label: str | None
    created_at: datetime


class PortalApiKeyRead(BaseModel):
    id: int
    key_prefix: str
    label: str | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


@router.post(
    "/me/portal-api-keys",
    response_model=PortalApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_portal_api_key(
    body: PortalApiKeyCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortalApiKeyCreated:
    settings = get_settings()
    row, raw = portal_keys_svc.create_portal_api_key(
        db,
        user_id=user.id,
        label=body.label,
        pepper=settings.portal_api_key_pepper,
    )
    return PortalApiKeyCreated(
        id=row.id,
        token=raw,
        key_prefix=row.key_prefix,
        label=row.label,
        created_at=row.created_at,
    )


@router.get("/me/portal-api-keys", response_model=list[PortalApiKeyRead])
def list_portal_api_keys(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PortalApiKeyRead]:
    rows = portal_keys_svc.list_keys_for_user(db, user.id)
    return [
        PortalApiKeyRead(
            id=r.id,
            key_prefix=r.key_prefix,
            label=r.label,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
        )
        for r in rows
    ]


@router.delete("/me/portal-api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_portal_api_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not portal_keys_svc.revoke_key(db, user_id=user.id, key_id=key_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="API key not found")
