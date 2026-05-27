"""FastAPI deps — require_actor / require_permission integration with RbacService."""

from __future__ import annotations

import secrets
import uuid as _uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tests.conftest import requires_postgres


def _rand_slug() -> str:
    return "rb-" + secrets.token_hex(4)


def _make_user(db, email: str, org_id):
    from ai_portal.auth.model import User

    user = User(
        email=email.lower(),
        uuid=_uuid.uuid4(),
        is_active=True,
        is_verified=False,
        role="member",
        org_id=org_id,
    )
    db.add(user)
    db.flush()
    return user


def _make_org(db, slug: str):
    from ai_portal.auth.model import Org

    org = Org(slug=slug, name=slug)
    db.add(org)
    db.flush()
    return org


# ── unit: Actor adapter ────────────────────────────────────────────────────────


def test_actor_from_user_returns_user_actor():
    from ai_portal.auth.model import User
    from ai_portal.control_plane.deps import actor_from_user

    u = User(id=42, email="a@b.com", uuid=_uuid.uuid4(), org_id=_uuid.uuid4())
    actor = actor_from_user(u)
    assert actor.kind == "user"
    assert actor.user_id == 42
    assert actor.org_id == u.org_id


def test_actor_from_user_without_org_raises():
    from ai_portal.auth.model import User
    from ai_portal.control_plane.deps import ActorWithoutOrg, actor_from_user

    u = User(id=1, email="a@b.com", uuid=_uuid.uuid4(), org_id=None)
    with pytest.raises(ActorWithoutOrg):
        actor_from_user(u)


# ── integration: require_permission gate ──────────────────────────────────────


@requires_postgres
def test_require_permission_denies_viewer_on_write():
    from ai_portal.auth.deps import get_current_user
    from ai_portal.auth.model import User
    from ai_portal.control_plane.deps import require_permission
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import RbacService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            user = _make_user(db, f"v-{secrets.token_hex(3)}@x.test", org.id)
            db.commit()
            RbacService(db).assign_system_role(
                org.id, user_id=user.id, role_name="viewer"
            )
            uid = user.id
    finally:
        db.close()

    app = FastAPI()

    def _fake_user():
        db2 = SessionLocal()
        try:
            from sqlalchemy import select

            u = db2.scalars(select(User).where(User.id == uid)).first()
            assert u is not None
            return u
        finally:
            db2.close()

    app.dependency_overrides[get_current_user] = _fake_user

    @app.post("/protected")
    def protected(_actor=Depends(require_permission("kb:create"))):
        return {"ok": True}

    @app.get("/readable")
    def readable(_actor=Depends(require_permission("usage:read"))):
        return {"ok": True}

    client = TestClient(app)
    # Viewer is denied write.
    r = client.post("/protected")
    assert r.status_code == 403
    assert "kb:create" in r.json()["detail"]
    # Viewer can read.
    r2 = client.get("/readable")
    assert r2.status_code == 200


@requires_postgres
def test_require_permission_allows_owner_anywhere():
    from ai_portal.auth.deps import get_current_user
    from ai_portal.auth.model import User
    from ai_portal.control_plane.deps import require_permission
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import RbacService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            user = _make_user(db, f"o-{secrets.token_hex(3)}@x.test", org.id)
            db.commit()
            RbacService(db).assign_system_role(
                org.id, user_id=user.id, role_name="owner"
            )
            uid = user.id
    finally:
        db.close()

    app = FastAPI()

    def _fake_user():
        db2 = SessionLocal()
        try:
            from sqlalchemy import select

            u = db2.scalars(select(User).where(User.id == uid)).first()
            return u
        finally:
            db2.close()

    app.dependency_overrides[get_current_user] = _fake_user

    @app.post("/x")
    def x(_actor=Depends(require_permission("kb:create"))):
        return {"ok": True}

    @app.post("/y")
    def y(_actor=Depends(require_permission("budgets:write"))):
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/x").status_code == 200
    assert client.post("/y").status_code == 200


@requires_postgres
def test_require_permission_unknown_perm_returns_500():
    """Unknown permission is a programming error — surface it loud."""
    from ai_portal.auth.deps import get_current_user
    from ai_portal.auth.model import User
    from ai_portal.control_plane.deps import require_permission
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import RbacService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            user = _make_user(db, f"u-{secrets.token_hex(3)}@x.test", org.id)
            db.commit()
            RbacService(db).assign_system_role(
                org.id, user_id=user.id, role_name="owner"
            )
            uid = user.id
    finally:
        db.close()

    app = FastAPI()

    def _fake_user():
        db2 = SessionLocal()
        try:
            from sqlalchemy import select

            u = db2.scalars(select(User).where(User.id == uid)).first()
            return u
        finally:
            db2.close()

    app.dependency_overrides[get_current_user] = _fake_user

    @app.post("/x")
    def x(_actor=Depends(require_permission("totally:bogus"))):
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/x")
    assert r.status_code == 500


def test_require_actor_alias_exported():
    """``require_actor`` is the public name for the current-user dep."""
    from ai_portal.control_plane.deps import require_actor

    assert callable(require_actor)


def test_facade_exports_deps():
    from ai_portal.control_plane import require_actor, require_permission

    assert callable(require_actor)
    assert callable(require_permission)
