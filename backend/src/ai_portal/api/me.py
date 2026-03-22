from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ai_portal.api.deps import get_app_roles, get_current_user
from ai_portal.api.rbac import require_app_roles
from ai_portal.models import User

router = APIRouter(prefix="/api", tags=["me"])


class MeRead(BaseModel):
    id: int
    email: str
    roles: list[str]


@router.get("/me", response_model=MeRead)
def read_me(
    request: Request,
    user: User = Depends(get_current_user),
) -> MeRead:
    return MeRead(id=user.id, email=user.email, roles=get_app_roles(request))


@router.get("/admin/ping")
def admin_ping(
    _: None = Depends(require_app_roles("Admin")),
) -> dict[str, str]:
    """RBAC probe: requires Entra app role `Admin` when auth_mode=entra (dev mode bypasses)."""
    return {"status": "ok"}
