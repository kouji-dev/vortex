"""Phase L1 — settings + module flags TDD.

Covers:
- Modules are enabled by default (no row).
- ``set_module_flag`` toggles the flag; ``is_module_enabled`` reflects it.
- ``assert_module_enabled`` returns 503 when disabled, passes when enabled.
- Feature gates default to False; ``set_feature_gate`` toggles a single key.
- KV: ``get_org_setting`` / ``set_org_setting`` roundtrip + default fallback.
"""

from __future__ import annotations

import secrets
import uuid as _uuid

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tests.conftest import requires_postgres


def _rand_slug() -> str:
    return "set-" + secrets.token_hex(4)


def _mk_org(db, slug: str):
    from ai_portal.auth.model import Org

    org = Org(slug=slug, name=slug)
    db.add(org)
    db.flush()
    return org


def _mk_user(db, email: str, org_id, role: str = "admin"):
    from ai_portal.auth.model import User

    user = User(
        email=email.lower(),
        uuid=_uuid.uuid4(),
        is_active=True,
        is_verified=True,
        role=role,
        org_id=org_id,
    )
    db.add(user)
    db.flush()
    return user


# ── Module enabled-by-default + toggle ──────────────────────────────────────


@requires_postgres
def test_module_enabled_by_default():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.settings.service import is_module_enabled

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, _rand_slug())
            db.commit()
            assert is_module_enabled(db, org_id=org.id, module="gateway") is True
            assert is_module_enabled(db, org_id=org.id, module="rag") is True
            assert is_module_enabled(db, org_id=org.id, module="workers") is True
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_set_module_flag_disables_then_reenables():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.settings.service import is_module_enabled, set_module_flag

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, _rand_slug())
            db.commit()
        set_module_flag(db, org_id=org.id, module="gateway", enabled=False)
        assert is_module_enabled(db, org_id=org.id, module="gateway") is False
        set_module_flag(db, org_id=org.id, module="gateway", enabled=True)
        assert is_module_enabled(db, org_id=org.id, module="gateway") is True
    finally:
        db.close()


# ── assert_module_enabled FastAPI dep ───────────────────────────────────────


@requires_postgres
def test_assert_module_enabled_returns_503_when_disabled():
    from ai_portal.auth.deps import get_current_user
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.settings.deps import assert_module_enabled
    from ai_portal.settings.service import set_module_flag

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, _rand_slug())
            user = _mk_user(db, f"a-{secrets.token_hex(3)}@x.test", org.id)
            db.commit()
            uid = user.id
            oid = org.id
    finally:
        db.close()

    app = FastAPI()

    def _fake_user():
        from sqlalchemy import select

        from ai_portal.auth.model import User

        d = SessionLocal()
        try:
            return d.scalars(select(User).where(User.id == uid)).first()
        finally:
            d.close()

    app.dependency_overrides[get_current_user] = _fake_user

    @app.get("/gw")
    def gateway_route(_=Depends(assert_module_enabled("gateway"))):
        return {"ok": True}

    client = TestClient(app)

    # Default: enabled → 200.
    r1 = client.get("/gw")
    assert r1.status_code == 200

    # Disable → 503.
    db2 = SessionLocal()
    try:
        set_module_flag(db2, org_id=oid, module="gateway", enabled=False)
    finally:
        db2.close()

    r2 = client.get("/gw")
    assert r2.status_code == 503
    assert "gateway" in r2.json()["detail"]


# ── Feature gates default False + toggle ────────────────────────────────────


@requires_postgres
def test_feature_gates_default_false():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.settings.service import (
        get_feature_gate,
        set_feature_gate,
        set_module_flag,
    )

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, _rand_slug())
            db.commit()
        # No row at all → False.
        assert get_feature_gate(
            db, org_id=org.id, module="rag", gate_key="search_providers.tavily"
        ) is False
        # Row exists but key missing → False.
        set_module_flag(db, org_id=org.id, module="rag", enabled=True)
        assert get_feature_gate(
            db, org_id=org.id, module="rag", gate_key="search_providers.tavily"
        ) is False
        # Toggle on.
        set_feature_gate(
            db, org_id=org.id, module="rag",
            gate_key="search_providers.tavily", value=True,
        )
        assert get_feature_gate(
            db, org_id=org.id, module="rag", gate_key="search_providers.tavily"
        ) is True
        # Toggle off.
        set_feature_gate(
            db, org_id=org.id, module="rag",
            gate_key="search_providers.tavily", value=False,
        )
        assert get_feature_gate(
            db, org_id=org.id, module="rag", gate_key="search_providers.tavily"
        ) is False
    finally:
        db.close()


# ── KV settings ─────────────────────────────────────────────────────────────


@requires_postgres
def test_org_setting_roundtrip():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.settings.service import get_org_setting, set_org_setting

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, _rand_slug())
            db.commit()
        # Missing → default returned.
        assert get_org_setting(db, org_id=org.id, key="missing") is None
        assert get_org_setting(
            db, org_id=org.id, key="missing", default="fallback"
        ) == "fallback"
        # Scalar.
        set_org_setting(db, org_id=org.id, key="brand_color", value="#0066ff")
        assert get_org_setting(db, org_id=org.id, key="brand_color") == "#0066ff"
        # Overwrite.
        set_org_setting(db, org_id=org.id, key="brand_color", value="#ff0000")
        assert get_org_setting(db, org_id=org.id, key="brand_color") == "#ff0000"
        # Dict.
        set_org_setting(
            db, org_id=org.id, key="retention",
            value={"audit_days": 2555, "usage_days": 365},
        )
        out = get_org_setting(db, org_id=org.id, key="retention")
        assert out == {"audit_days": 2555, "usage_days": 365}
    finally:
        db.close()


# ── Routes wired ────────────────────────────────────────────────────────────


def test_settings_router_exposes_expected_paths():
    """Test against the router in isolation — independent of main.py wiring."""
    from ai_portal.settings.router import router

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/v1/settings" in paths
    assert "/v1/module-flags" in paths


def test_settings_router_methods():
    """Both endpoints expose GET and PATCH."""
    from ai_portal.settings.router import router

    methods_by_path: dict[str, set[str]] = {}
    for r in router.routes:  # type: ignore[attr-defined]
        methods_by_path.setdefault(r.path, set()).update(r.methods or set())
    assert {"GET", "PATCH"}.issubset(methods_by_path["/v1/settings"])
    assert {"GET", "PATCH"}.issubset(methods_by_path["/v1/module-flags"])


# ── Facade re-export ────────────────────────────────────────────────────────


def test_control_plane_facade_exports_settings():
    from ai_portal import control_plane

    assert hasattr(control_plane, "is_module_enabled")
    assert hasattr(control_plane, "set_module_flag")
    assert hasattr(control_plane, "get_org_setting")
    assert hasattr(control_plane, "set_org_setting")
    assert hasattr(control_plane, "get_feature_gate")
    assert hasattr(control_plane, "set_feature_gate")
    assert hasattr(control_plane, "assert_module_enabled")
