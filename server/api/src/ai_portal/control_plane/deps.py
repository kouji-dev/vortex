"""FastAPI dependencies for the control plane.

Public surface used by every other module:

- :func:`require_actor` — yields the authenticated :class:`Actor` (alias of
  ``get_current_user`` + adapter)
- :func:`require_permission` — builds a route dep that 403s when the actor
  lacks the named permission

Example::

    from ai_portal.control_plane import require_permission

    @router.post("/kb")
    def create_kb(_=Depends(require_permission("kb:create"))):
        ...

Resource-scoped checks pass a ``resource`` dict via
``Depends(require_permission("kb:read", resource_from=lambda r: {"kb_id": r.path_params["id"]}))``
— see ``require_permission_scoped`` below.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.rbac.service import Actor, RbacService, UnknownPermission


class ActorWithoutOrg(Exception):
    """Raised when the authenticated user has no org_id (cannot scope RBAC)."""


def actor_from_user(user: User) -> Actor:
    """Build an :class:`Actor` for the authenticated user.

    Raises :class:`ActorWithoutOrg` if the user has no ``org_id`` — the
    permission system is org-scoped and a user without an org has nothing to
    check against.
    """
    if user.org_id is None:
        raise ActorWithoutOrg(f"user {user.id} has no org_id")
    return Actor(kind="user", user_id=user.id, org_id=user.org_id)


def require_actor(user: User = Depends(get_current_user)) -> Actor:
    """Resolve the caller as an :class:`Actor`."""
    try:
        return actor_from_user(user)
    except ActorWithoutOrg as e:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="actor has no org"
        ) from e


def get_rbac_service(db: Session = Depends(get_db)) -> RbacService:
    return RbacService(db)


def require_permission(perm: str) -> Callable:
    """Build a dependency that 403s unless the caller holds *perm*.

    Unknown ``perm`` → 500 (programming error, not a client problem).
    """

    def _dep(
        actor: Actor = Depends(require_actor),
        rbac: RbacService = Depends(get_rbac_service),
    ) -> Actor:
        try:
            allowed = rbac.has_permission(actor, perm)
        except UnknownPermission as e:
            # Surface as 500 — the route declared a perm not in the catalog.
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"unknown permission key: {perm}",
            ) from e
        if not allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"missing permission: {perm}",
            )
        return actor

    return _dep


def require_permission_scoped(
    perm: str,
    resource_from: Callable[[Request], dict],
) -> Callable:
    """Like :func:`require_permission` but evaluates a resource scope.

    ``resource_from`` is called with the incoming :class:`Request` and must
    return a dict (e.g. ``{"kb_id": "<uuid>"}``). The check passes if any of
    the actor's grants matches the resource per
    :meth:`RbacService.has_permission`.
    """

    def _dep(
        request: Request,
        actor: Actor = Depends(require_actor),
        rbac: RbacService = Depends(get_rbac_service),
    ) -> Actor:
        resource = resource_from(request)
        try:
            allowed = rbac.has_permission(actor, perm, resource=resource)
        except UnknownPermission as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"unknown permission key: {perm}",
            ) from e
        if not allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"missing permission: {perm}",
            )
        return actor

    return _dep
