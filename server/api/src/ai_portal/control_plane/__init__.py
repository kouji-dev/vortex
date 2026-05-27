"""Control plane facade — single import surface for cross-module helpers.

Modules in this suite should depend on ``ai_portal.control_plane`` rather
than reaching into peer domains directly. Today this re-exports a minimal
set; it grows as Phase A–P land.
"""
from __future__ import annotations

from ai_portal.control_plane.deps import (  # noqa: F401
    Actor,
    ActorWithoutOrg,
    actor_from_user,
    get_rbac_service,
    require_actor,
    require_permission,
    require_permission_scoped,
)
from ai_portal.control_plane.webhook_stub import emit_webhook  # noqa: F401

__all__ = [
    "Actor",
    "ActorWithoutOrg",
    "actor_from_user",
    "emit_webhook",
    "get_rbac_service",
    "require_actor",
    "require_permission",
    "require_permission_scoped",
]
