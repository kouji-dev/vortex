"""RBAC roles + role_permissions + actor_role_assignments + has_permission."""

from __future__ import annotations

import secrets
import uuid as _uuid

import pytest

from tests.conftest import requires_postgres


def _rand_slug() -> str:
    return "rb-" + secrets.token_hex(4)


def _make_user(db, email: str):
    from ai_portal.auth.model import User

    user = User(
        email=email.lower(),
        uuid=_uuid.uuid4(),
        is_active=True,
        is_verified=False,
        role="member",
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


# ── Models ────────────────────────────────────────────────────────────────────


def test_role_model_has_columns():
    from ai_portal.rbac.model import Role

    cols = {c.name for c in Role.__table__.columns}
    assert {"id", "org_id", "name", "description", "is_system", "created_at"} <= cols


def test_role_permission_model_columns():
    from ai_portal.rbac.model import RolePermission

    cols = {c.name for c in RolePermission.__table__.columns}
    assert {"role_id", "permission_key", "resource_scope"} <= cols


def test_actor_role_assignment_columns():
    from ai_portal.rbac.model import ActorRoleAssignment

    cols = {c.name for c in ActorRoleAssignment.__table__.columns}
    assert {
        "id",
        "org_id",
        "role_id",
        "actor_user_id",
        "actor_api_key_id",
        "resource_scope",
        "created_at",
    } <= cols


# ── Built-in role seeding ─────────────────────────────────────────────────────


@requires_postgres
def test_builtin_system_roles_seeded():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.model import Role
    from sqlalchemy import select

    db = SessionLocal()
    try:
        names = set(
            db.scalars(
                select(Role.name).where(Role.is_system.is_(True), Role.org_id.is_(None))
            ).all()
        )
        assert {"owner", "admin", "member", "viewer", "service"} <= names
    finally:
        db.close()


@requires_postgres
def test_owner_role_has_all_permissions():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.catalog import PERMISSIONS
    from ai_portal.rbac.model import Role, RolePermission
    from sqlalchemy import select

    db = SessionLocal()
    try:
        owner = db.scalars(
            select(Role).where(Role.name == "owner", Role.is_system.is_(True))
        ).first()
        assert owner is not None
        perm_keys = set(
            db.scalars(
                select(RolePermission.permission_key).where(
                    RolePermission.role_id == owner.id
                )
            ).all()
        )
        assert perm_keys == {p.key for p in PERMISSIONS}
    finally:
        db.close()


@requires_postgres
def test_viewer_role_has_only_read_permissions():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.model import Role, RolePermission
    from sqlalchemy import select

    db = SessionLocal()
    try:
        viewer = db.scalars(
            select(Role).where(Role.name == "viewer", Role.is_system.is_(True))
        ).first()
        assert viewer is not None
        perm_keys = set(
            db.scalars(
                select(RolePermission.permission_key).where(
                    RolePermission.role_id == viewer.id
                )
            ).all()
        )
        # viewer = read-only; no write/delete/admin/revoke/invite/create/submit
        for k in perm_keys:
            tail = k.split(":")[-1]
            assert tail in {"read"}, f"viewer should not have {k}"


    finally:
        db.close()


# ── has_permission service ────────────────────────────────────────────────────


@requires_postgres
def test_has_permission_owner_passes_any_check():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.service import RbacService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            user = _make_user(db, f"o-{secrets.token_hex(3)}@x.test")
            user.org_id = org.id
            db.commit()
            svc = RbacService(db)
            svc.assign_system_role(org.id, user_id=user.id, role_name="owner")

            from ai_portal.rbac.service import Actor

            actor = Actor(user_id=user.id, org_id=org.id, kind="user")
            assert svc.has_permission(actor, "kb:create")
            assert svc.has_permission(actor, "gateway:complete")
            assert svc.has_permission(actor, "audit:read")
            assert svc.has_permission(actor, "budgets:write")
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_has_permission_viewer_blocks_writes():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.service import Actor, RbacService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            user = _make_user(db, f"v-{secrets.token_hex(3)}@x.test")
            user.org_id = org.id
            db.commit()
            svc = RbacService(db)
            svc.assign_system_role(org.id, user_id=user.id, role_name="viewer")
            actor = Actor(user_id=user.id, org_id=org.id, kind="user")
            assert svc.has_permission(actor, "audit:read")
            assert svc.has_permission(actor, "usage:read")
            assert not svc.has_permission(actor, "kb:create")
            assert not svc.has_permission(actor, "budgets:write")
            assert not svc.has_permission(actor, "members:invite")
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_has_permission_unknown_perm_raises():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.service import Actor, RbacService, UnknownPermission

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            user = _make_user(db, f"u-{secrets.token_hex(3)}@x.test")
            user.org_id = org.id
            db.commit()
            svc = RbacService(db)
            svc.assign_system_role(org.id, user_id=user.id, role_name="member")
            actor = Actor(user_id=user.id, org_id=org.id, kind="user")
            with pytest.raises(UnknownPermission):
                svc.has_permission(actor, "made-up:permission")
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_has_permission_no_assignment_denies():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.service import Actor, RbacService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            user = _make_user(db, f"n-{secrets.token_hex(3)}@x.test")
            user.org_id = org.id
            db.commit()
            svc = RbacService(db)
            actor = Actor(user_id=user.id, org_id=org.id, kind="user")
            # No role assignment → deny.
            assert not svc.has_permission(actor, "kb:read")
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_has_permission_service_actor_via_api_key():
    """API-key actors check their own role assignment."""
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.service import Actor, RbacService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            db.commit()
            svc = RbacService(db)
            # Synthetic api_key_id stand-in (rows assigned to api keys live in
            # actor_role_assignments via actor_api_key_id).
            api_key_id = secrets.randbelow(2**31)
            svc.assign_system_role(
                org.id, api_key_id=api_key_id, role_name="service"
            )
            actor = Actor(api_key_id=api_key_id, org_id=org.id, kind="api_key")
            # ``service`` role has gateway:complete by default.
            assert svc.has_permission(actor, "gateway:complete")
            assert not svc.has_permission(actor, "settings:write")
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_resource_scope_check():
    """Permission with resource_scope restricts to matching resource_id."""
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.service import Actor, RbacService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _make_org(db, _rand_slug())
            user = _make_user(db, f"r-{secrets.token_hex(3)}@x.test")
            user.org_id = org.id
            db.commit()
            svc = RbacService(db)
            # Assign viewer scoped to a specific KB id only.
            kb_id = str(_uuid.uuid4())
            svc.assign_system_role(
                org.id,
                user_id=user.id,
                role_name="viewer",
                resource_scope={"kb_id": kb_id},
            )
            actor = Actor(user_id=user.id, org_id=org.id, kind="user")
            # Allowed on this KB.
            assert svc.has_permission(actor, "kb:read", resource={"kb_id": kb_id})
            # Denied on different KB.
            other = str(_uuid.uuid4())
            assert not svc.has_permission(actor, "kb:read", resource={"kb_id": other})
    finally:
        db.rollback()
        db.close()
