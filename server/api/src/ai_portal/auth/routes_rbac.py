from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from ai_portal.auth.deps import get_app_roles, get_current_user
from ai_portal.auth.model import User


def require_app_roles(*allowed: str) -> Callable[..., None]:
    """Require at least one app role (from OIDC access token)."""

    def checker(
        request: Request,
        _user: User = Depends(get_current_user),
    ) -> None:
        if not allowed:
            return
        roles = set(get_app_roles(request))
        if not roles.intersection(allowed):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Insufficient application role",
            )

    return checker
