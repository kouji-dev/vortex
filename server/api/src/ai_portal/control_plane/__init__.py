"""Control plane facade — single import surface for cross-module helpers.

Every downstream module (gateway, rag, memories, workers, chat, ...) imports
control-plane services from **this** module rather than reaching into peer
domains directly. The shape here is the stable contract — refactors of the
underlying domains must keep these names + signatures intact.

Public surface, grouped by concern:

- **auth / actor**:  ``Actor``, ``ActorWithoutOrg``, ``actor_from_user``,
  ``current_actor``, ``require_actor``
- **rbac**:          ``Permission``, ``RbacService``, ``UnknownPermission``,
  ``get_rbac_service``, ``has_permission``, ``rbac_evaluate``,
  ``require_permission``, ``require_permission_scoped``
- **audit**:         ``emit_audit``, ``AuditSink``, ``AuditEventPayload``
- **usage**:         ``emit_usage``, ``check_quota``
- **webhooks**:      ``emit_webhook``
- **settings**:      ``assert_module_enabled``, ``get_feature_gate``,
  ``get_org_setting``, ``is_module_enabled``, ``set_feature_gate``,
  ``set_module_flag``, ``set_org_setting``, ``KNOWN_MODULES``
- **storage**:       ``BlobStore``, ``BlobNotFound``, ``build_blob_store``
- **notify**:        ``NotifyService``, ``Channel``, ``send_event``
- **api keys**:      ``ApiKeyService``
- **gdpr**:          ``register_exporter``, ``register_deleter``
- **type aliases**:  ``ModuleName``, ``PermissionKey``

The facade is import-safe: re-importing it is idempotent, and importing it
must not trigger network / DB side effects (each helper resolves its
dependencies lazily).
"""
from __future__ import annotations

# ── auth / actor ─────────────────────────────────────────────────────────────
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

# ── rbac ─────────────────────────────────────────────────────────────────────
from ai_portal.rbac.catalog import Permission  # noqa: F401
from ai_portal.rbac.evaluator import evaluate as rbac_evaluate  # noqa: F401
from ai_portal.rbac.service import RbacService, UnknownPermission  # noqa: F401

# ── audit ────────────────────────────────────────────────────────────────────
from ai_portal.audit.protocol import AuditEventPayload, AuditSink  # noqa: F401
from ai_portal.audit.service import emit_audit  # noqa: F401

# ── usage ────────────────────────────────────────────────────────────────────
from ai_portal.usage.emit import emit_usage  # noqa: F401
from ai_portal.usage.service import check_quota  # noqa: F401

# ── webhooks ─────────────────────────────────────────────────────────────────
# NOTE: keep the stub-shape ``emit_webhook(event_type, payload, org_id)`` here.
# Phase F3 has shipped the real dispatcher; callers that need the DB-bound
# signature import ``ai_portal.webhooks.emit_webhook`` directly. The facade
# exposes the no-arg shape so cross-cutting code (budgets, audit, settings)
# stays decoupled from the session lifecycle.
from ai_portal.control_plane.webhook_stub import emit_webhook  # noqa: F401

# ── settings + module flags ──────────────────────────────────────────────────
from ai_portal.settings import (  # noqa: F401
    KNOWN_MODULES,
    assert_module_enabled,
    get_feature_gate,
    get_org_setting,
    is_module_enabled,
    set_feature_gate,
    set_module_flag,
    set_org_setting,
)

# ── storage ──────────────────────────────────────────────────────────────────
from ai_portal.storage import BlobNotFound, BlobStore, build_blob_store  # noqa: F401

# ── notify ───────────────────────────────────────────────────────────────────
from ai_portal.notify import Channel, NotifyService, send_event  # noqa: F401

# ── api keys ─────────────────────────────────────────────────────────────────
from ai_portal.api_keys.service import ApiKeyService  # noqa: F401

# ── gdpr ─────────────────────────────────────────────────────────────────────
from ai_portal.gdpr.registry import (  # noqa: F401
    register_deleter,
    register_exporter,
)

# ── type aliases ─────────────────────────────────────────────────────────────
from ai_portal.control_plane._types import ModuleName, PermissionKey  # noqa: F401


__all__ = [
    # auth / actor
    "Actor",
    "ActorWithoutOrg",
    "actor_from_user",
    "current_actor",
    "require_actor",
    # rbac
    "Permission",
    "RbacService",
    "UnknownPermission",
    "get_rbac_service",
    "has_permission",
    "rbac_evaluate",
    "require_permission",
    "require_permission_scoped",
    # audit
    "AuditEventPayload",
    "AuditSink",
    "emit_audit",
    # usage
    "check_quota",
    "emit_usage",
    # webhooks
    "emit_webhook",
    # settings
    "KNOWN_MODULES",
    "assert_module_enabled",
    "get_feature_gate",
    "get_org_setting",
    "is_module_enabled",
    "set_feature_gate",
    "set_module_flag",
    "set_org_setting",
    # storage
    "BlobNotFound",
    "BlobStore",
    "build_blob_store",
    # notify
    "Channel",
    "NotifyService",
    "send_event",
    # api keys
    "ApiKeyService",
    # gdpr
    "register_deleter",
    "register_exporter",
    # type aliases
    "ModuleName",
    "PermissionKey",
]


def has_permission(actor: Actor, perm: str, *, resource: dict | None = None) -> bool:
    """Module-level convenience: check a permission without holding an RbacService.

    Opens a short-lived session, defers to :meth:`RbacService.has_permission`,
    and returns the bool. Use the class form when batching many checks.
    """
    from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415

    with SessionLocal() as db:
        return RbacService(db).has_permission(actor, perm, resource=resource)
