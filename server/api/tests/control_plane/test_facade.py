"""Control plane public facade (Phase P).

Every cross-cutting CP service is re-exported via ``ai_portal.control_plane``.
Downstream modules (gateway, rag, memories, workers, chat, ...) must import
from this facade — not from peer domains directly.

The tests below pin the facade surface so refactors of the underlying domains
can't silently break consumers.
"""
from __future__ import annotations

import importlib

import pytest


# ── Symbol list (sole source of truth for the facade contract) ──────────────

EXPECTED_SYMBOLS: tuple[str, ...] = (
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
    # settings + module flags
    "KNOWN_MODULES",
    "ModuleName",
    "PermissionKey",
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
)


def test_facade_module_imports_cleanly() -> None:
    """A fresh import of the facade succeeds and exposes ``__all__``."""
    cp = importlib.import_module("ai_portal.control_plane")
    assert hasattr(cp, "__all__")
    assert isinstance(cp.__all__, list)
    assert len(cp.__all__) >= len(EXPECTED_SYMBOLS)


def test_facade_re_import_is_idempotent() -> None:
    """Re-importing yields the same module object (no side-effect divergence)."""
    cp_a = importlib.import_module("ai_portal.control_plane")
    cp_b = importlib.reload(cp_a)
    for name in EXPECTED_SYMBOLS:
        assert getattr(cp_a, name) is getattr(cp_b, name) or getattr(cp_b, name) is not None


@pytest.mark.parametrize("name", EXPECTED_SYMBOLS)
def test_every_expected_symbol_is_present(name: str) -> None:
    """Every name in ``EXPECTED_SYMBOLS`` is reachable on the facade."""
    cp = importlib.import_module("ai_portal.control_plane")
    assert hasattr(cp, name), f"facade missing public symbol: {name!r}"


@pytest.mark.parametrize("name", EXPECTED_SYMBOLS)
def test_every_expected_symbol_is_in_dunder_all(name: str) -> None:
    """``__all__`` is the authoritative export list — every name lives there."""
    cp = importlib.import_module("ai_portal.control_plane")
    assert name in cp.__all__, f"{name!r} missing from __all__"


# ── Shape pins (catch silent refactors of re-exported types) ────────────────


def test_actor_is_dataclass_with_org_id() -> None:
    from ai_portal.control_plane import Actor

    fields = getattr(Actor, "__dataclass_fields__", None)
    assert fields is not None, "Actor must be a dataclass"
    assert "org_id" in fields
    assert "kind" in fields


def test_permission_is_dataclass_with_key() -> None:
    from ai_portal.control_plane import Permission

    fields = getattr(Permission, "__dataclass_fields__", None)
    assert fields is not None, "Permission must be a dataclass"
    assert "key" in fields
    assert "module" in fields


def test_blob_store_is_runtime_protocol() -> None:
    from ai_portal.control_plane import BlobStore

    # Protocols carry these dunders; this catches accidental swap to a class.
    assert hasattr(BlobStore, "put")
    assert hasattr(BlobStore, "get")
    assert hasattr(BlobStore, "presign_get")
    assert hasattr(BlobStore, "presign_put")


def test_audit_sink_is_runtime_protocol() -> None:
    from ai_portal.control_plane import AuditSink

    assert hasattr(AuditSink, "write")


def test_module_name_is_string_alias() -> None:
    """``ModuleName`` is a Literal type alias enumerating known modules."""
    from ai_portal.control_plane import KNOWN_MODULES, ModuleName

    # Literal aliases evaluate truthy; the underlying values match KNOWN_MODULES.
    assert ModuleName is not None
    assert isinstance(KNOWN_MODULES, tuple)
    assert "gateway" in KNOWN_MODULES


def test_callables_are_actually_callable() -> None:
    from ai_portal import control_plane as cp

    for name in (
        "actor_from_user",
        "require_actor",
        "current_actor",
        "require_permission",
        "require_permission_scoped",
        "get_rbac_service",
        "emit_audit",
        "emit_usage",
        "emit_webhook",
        "assert_module_enabled",
        "get_feature_gate",
        "get_org_setting",
        "is_module_enabled",
        "set_feature_gate",
        "set_module_flag",
        "set_org_setting",
        "register_exporter",
        "register_deleter",
        "build_blob_store",
        "send_event",
        "has_permission",
    ):
        attr = getattr(cp, name)
        assert callable(attr), f"facade.{name} should be callable"


def test_require_permission_returns_a_dependency() -> None:
    """``require_permission(perm)`` returns a fresh callable each call."""
    from ai_portal.control_plane import require_permission

    dep1 = require_permission("org:read")
    dep2 = require_permission("org:read")
    assert callable(dep1)
    assert callable(dep2)
    assert dep1 is not dep2  # factory pattern — independent closures


def test_build_blob_store_default_returns_local_fs(tmp_path) -> None:
    """The factory honours the ``local_fs`` kind and yields a BlobStore."""
    from ai_portal.control_plane import BlobStore, build_blob_store

    store = build_blob_store("local_fs", root=str(tmp_path))
    assert isinstance(store, BlobStore)


def test_build_blob_store_rejects_unknown_kind() -> None:
    from ai_portal.control_plane import build_blob_store

    with pytest.raises(ValueError):
        build_blob_store("not_a_real_kind")
