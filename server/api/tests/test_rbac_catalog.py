"""Permission catalog — single source of truth across modules."""

from __future__ import annotations

import pytest


def test_catalog_imports_and_has_min_count():
    from ai_portal.rbac.catalog import PERMISSIONS

    assert isinstance(PERMISSIONS, list)
    assert len(PERMISSIONS) >= 30


def test_catalog_keys_unique():
    from ai_portal.rbac.catalog import PERMISSIONS

    keys = [p.key for p in PERMISSIONS]
    assert len(keys) == len(set(keys)), "duplicate permission keys"


def test_catalog_covers_all_modules():
    from ai_portal.rbac.catalog import PERMISSIONS

    modules = {p.module for p in PERMISSIONS}
    # control_plane, gateway, rag, memories, workers
    assert {"control_plane", "gateway", "rag", "memories", "workers"} <= modules


def test_catalog_key_format():
    """Keys must be ``namespace:action`` lowercase."""
    from ai_portal.rbac.catalog import PERMISSIONS

    for p in PERMISSIONS:
        assert ":" in p.key, f"bad key {p.key}"
        assert p.key == p.key.lower(), f"key must be lowercase: {p.key}"
        assert p.description, f"missing description for {p.key}"


def test_catalog_has_expected_control_plane_perms():
    from ai_portal.rbac.catalog import PERMISSIONS

    keys = {p.key for p in PERMISSIONS}
    expected = {
        "org:read",
        "org:update",
        "members:read",
        "members:invite",
        "members:remove",
        "api-keys:create",
        "api-keys:read",
        "api-keys:revoke",
        "audit:read",
        "audit:export",
        "usage:read",
        "budgets:read",
        "budgets:write",
        "webhooks:read",
        "webhooks:write",
        "settings:read",
        "settings:write",
        "rbac:read",
        "rbac:write",
    }
    assert expected <= keys


def test_catalog_has_gateway_perms():
    from ai_portal.rbac.catalog import PERMISSIONS

    keys = {p.key for p in PERMISSIONS}
    assert {
        "gateway:complete",
        "gateway:embed",
        "gateway:admin",
        "gateway:traces:read",
        "gateway:replay",
    } <= keys


def test_catalog_has_rag_perms():
    from ai_portal.rbac.catalog import PERMISSIONS

    keys = {p.key for p in PERMISSIONS}
    assert {
        "kb:create",
        "kb:read",
        "kb:write",
        "kb:delete",
        "kb:answer",
        "kb:eval",
    } <= keys


def test_catalog_has_memories_perms():
    from ai_portal.rbac.catalog import PERMISSIONS

    keys = {p.key for p in PERMISSIONS}
    assert {"memory:read", "memory:write", "memory:admin"} <= keys


def test_catalog_has_workers_perms():
    from ai_portal.rbac.catalog import PERMISSIONS

    keys = {p.key for p in PERMISSIONS}
    assert {"workers:submit", "workers:approve", "workers:admin"} <= keys


def test_permission_by_key_lookup():
    from ai_portal.rbac.catalog import permission_by_key

    p = permission_by_key("org:read")
    assert p is not None
    assert p.module == "control_plane"
    assert permission_by_key("does-not-exist") is None
