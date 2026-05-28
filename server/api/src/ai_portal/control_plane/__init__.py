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
    current_actor,
    get_rbac_service,
    require_actor,
    require_permission,
    require_permission_scoped,
)
from ai_portal.control_plane.webhook_stub import emit_webhook  # noqa: F401
from ai_portal.gdpr.registry import (  # noqa: F401
    register_deleter,
    register_exporter,
)
from ai_portal.settings import (  # noqa: F401
    assert_module_enabled,
    get_feature_gate,
    get_org_setting,
    is_module_enabled,
    set_feature_gate,
    set_module_flag,
    set_org_setting,
)

__all__ = [
    "Actor",
    "ActorWithoutOrg",
    "actor_from_user",
    "assert_module_enabled",
    "current_actor",
    "emit_webhook",
    "get_feature_gate",
    "get_org_setting",
    "get_rbac_service",
    "is_module_enabled",
    "register_deleter",
    "register_exporter",
    "require_actor",
    "require_permission",
    "require_permission_scoped",
    "set_feature_gate",
    "set_module_flag",
    "set_org_setting",
]
