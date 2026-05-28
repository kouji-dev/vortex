"""FastAPI dependency: ``assert_module_enabled``.

Use on any route that belongs to a togglable module. Returns 503 if the
calling actor's org has disabled the module.

Example::

    from ai_portal.settings import assert_module_enabled

    @router.post("/v1/gateway/complete")
    def gateway_complete(
        _=Depends(assert_module_enabled("gateway")),
    ):
        ...
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.settings.service import is_module_enabled


def assert_module_enabled(module: str) -> Callable:
    """Build a dep that 503s if ``module`` is disabled for the actor's org."""

    def _dep(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if user.org_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="actor has no org"
            )
        if not is_module_enabled(db, org_id=user.org_id, module=module):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"module disabled: {module}",
            )
        return user

    return _dep
