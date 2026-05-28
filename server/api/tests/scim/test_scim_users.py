"""H1: SCIM provisioning — users + groups + endpoint auth + cascade revoke.

Postgres-backed because the SCIM tables + RLS policies live there. The router
is exercised via FastAPI's TestClient so bearer-token auth is end-to-end.
"""

from __future__ import annotations

import secrets
import uuid as _uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

# Ensure ORM mappers register before any flush.
import ai_portal.api_keys.model  # noqa: F401
import ai_portal.auth.model  # noqa: F401
import ai_portal.scim.model  # noqa: F401
from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> _uuid.UUID:
    org_id = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'SCIM') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


@pytest.fixture
def scim_app():
    """Bare app mounting only the SCIM wire router."""
    from ai_portal.scim.router import scim_router

    app = FastAPI()
    app.include_router(scim_router)
    return TestClient(app)


# ── service-level tests ──────────────────────────────────────────────────────


@requires_postgres
def test_endpoint_create_returns_plaintext_once_and_hashes_token():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import (
        TOKEN_PREFIX,
        ScimEndpointService,
        hash_scim_token,
    )

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-mint")
            created = ScimEndpointService(db).create_endpoint(
                org_id=org_id, name="okta-prod", preset="okta"
            )
            assert created.token.startswith(TOKEN_PREFIX)
            assert created.endpoint.token_hash == hash_scim_token(created.token)
            # Plaintext appears nowhere on the row.
            assert created.token not in (
                created.endpoint.name,
                created.endpoint.token_hash,
                str(created.endpoint.id),
            )
            assert created.endpoint.preset == "okta"
            assert created.endpoint.enabled is True
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_resolve_token_rejects_unknown_and_revoked():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import (
        ScimEndpointService,
        ScimUnauthorized,
    )

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-token")
            svc = ScimEndpointService(db)
            created = svc.create_endpoint(org_id=org_id, name="probe")

            # Live token resolves.
            row = svc.resolve_token(created.token)
            assert row.id == created.endpoint.id

            # Garbage token rejected.
            with pytest.raises(ScimUnauthorized):
                svc.resolve_token("not-a-scim-token")
            with pytest.raises(ScimUnauthorized):
                svc.resolve_token(None)

            # Revoked endpoint rejected.
            svc.revoke_endpoint(org_id=org_id, endpoint_id=created.endpoint.id)
            with pytest.raises(ScimUnauthorized):
                svc.resolve_token(created.token)
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_create_user_persists_and_emits_scim_id():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import ScimEndpointService, ScimProvisioner

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-cu")
            ep = ScimEndpointService(db).create_endpoint(
                org_id=org_id, name="ep", preset="generic"
            )
            prov = ScimProvisioner(db, ep.endpoint)
            tag = secrets.token_hex(4)
            email = f"alice-{tag}@acme.test"
            ext_id = f"ext-A-{tag}"
            result = prov.create_user(
                {
                    "userName": email,
                    "externalId": ext_id,
                    "emails": [{"value": email, "primary": True}],
                    "name": {"givenName": "Alice"},
                    "active": True,
                }
            )
            assert result.created is True
            assert result.user.email == email
            assert result.user.scim_external_id == ext_id
            assert result.user.org_id == org_id
            assert result.user.is_active is True

            # SCIM lookup by external id resolves the same row.
            looked = prov.get_user_by_scim_id(ext_id)
            assert looked.id == result.user.id
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_deactivate_user_revokes_sessions_and_scopes_api_keys():
    """The spec calls for deactivation to revoke sessions + scope keys.

    We assert both: every active :class:`UserSession` row and every active
    :class:`ApiKey` for the user gets ``revoked_at`` set.
    """
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.auth.sessions import create_session
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import ScimEndpointService, ScimProvisioner

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-deact")
            ep = ScimEndpointService(db).create_endpoint(
                org_id=org_id, name="ep", preset="generic"
            )
            prov = ScimProvisioner(db, ep.endpoint)
            tag = secrets.token_hex(4)
            email = f"deact-{tag}@acme.test"
            ext_id = f"ext-DEACT-{tag}"
            res = prov.create_user(
                {
                    "userName": email,
                    "externalId": ext_id,
                    "emails": [{"value": email}],
                    "active": True,
                }
            )
            user = res.user

            sess = create_session(
                db,
                user_id=user.id,
                refresh_token=secrets.token_hex(16),
                ip="127.0.0.1",
                user_agent="probe",
            )
            assert sess.revoked_at is None

            key_created = ApiKeyService(db).create(
                org_id=org_id,
                name="probe",
                scopes=["gateway:complete"],
                actor_user_id=user.id,
            )
            assert key_created.key.revoked_at is None

            # PATCH active=false -> deactivation cascade.
            prov.patch_user(
                ext_id,
                {"Operations": [{"op": "replace", "path": "active", "value": False}]},
            )

            db.refresh(sess)
            assert sess.revoked_at is not None

            from sqlalchemy import select

            from ai_portal.api_keys.model import ApiKey

            key_rows = db.scalars(
                select(ApiKey).where(ApiKey.actor_user_id == user.id)
            ).all()
            assert key_rows, "key persisted"
            assert all(k.revoked_at is not None for k in key_rows)
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_create_user_with_active_false_immediately_deactivates():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import ScimEndpointService, ScimProvisioner

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-inact")
            ep = ScimEndpointService(db).create_endpoint(
                org_id=org_id, name="ep", preset="generic"
            )
            prov = ScimProvisioner(db, ep.endpoint)
            tag = secrets.token_hex(4)
            email = f"inactive-{tag}@acme.test"
            res = prov.create_user(
                {
                    "userName": email,
                    "externalId": f"ext-INACTIVE-{tag}",
                    "emails": [{"value": email}],
                    "active": False,
                }
            )
            assert res.user.is_active is False
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_create_group_with_member_resolves_to_existing_user():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.model import ScimGroupMember
    from ai_portal.scim.service import ScimEndpointService, ScimProvisioner

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-grp")
            ep = ScimEndpointService(db).create_endpoint(
                org_id=org_id, name="ep", preset="generic"
            )
            prov = ScimProvisioner(db, ep.endpoint)
            tag = secrets.token_hex(4)
            email = f"groupie-{tag}@acme.test"
            ext_uid = f"ext-G1-{tag}"
            user_res = prov.create_user(
                {
                    "userName": email,
                    "externalId": ext_uid,
                    "emails": [{"value": email}],
                }
            )
            group_name = f"Engineers-{tag}"
            group = prov.create_group(
                {
                    "displayName": group_name,
                    "externalId": f"g-eng-{tag}",
                    "members": [{"value": ext_uid, "display": email}],
                }
            )
            assert group.display_name == group_name

            from sqlalchemy import select

            members = db.scalars(
                select(ScimGroupMember).where(ScimGroupMember.group_id == group.id)
            ).all()
            assert len(members) == 1
            assert members[0].user_id == user_res.user.id
            assert members[0].external_user_id == ext_uid
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_endpoint_admin_group_role_mapping_is_upsert():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import ScimEndpointService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-role")
            svc = ScimEndpointService(db)
            ep = svc.create_endpoint(org_id=org_id, name="ep", preset="generic")
            display_name = f"Engineers-{secrets.token_hex(4)}"
            row1 = svc.set_group_role(
                endpoint_id=ep.endpoint.id,
                org_id=org_id,
                display_name=display_name,
                role_name="admin",
            )
            assert row1.role_name == "admin"

            # Re-mapping same display_name updates in place.
            row2 = svc.set_group_role(
                endpoint_id=ep.endpoint.id,
                org_id=org_id,
                display_name=display_name,
                role_name="member",
            )
            assert row2.id == row1.id
            assert row2.role_name == "member"
            db.commit()
    finally:
        db.rollback()
        db.close()


# ── wire router tests ───────────────────────────────────────────────────────


@requires_postgres
def test_scim_users_post_requires_bearer_token(scim_app):
    r = scim_app.post(
        "/scim/v2/Users",
        json={"userName": "x@y.com", "emails": [{"value": "x@y.com"}]},
    )
    assert r.status_code == 401


@requires_postgres
def test_scim_users_post_with_valid_token_creates_user(scim_app):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import ScimEndpointService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-wire")
            ep = ScimEndpointService(db).create_endpoint(
                org_id=org_id, name="wire", preset="generic"
            )
            token = ep.token
            db.commit()
    finally:
        db.close()

    tag = secrets.token_hex(4)
    email = f"wire-{tag}@acme.test"
    ext_id = f"wire-{tag}"
    r = scim_app.post(
        "/scim/v2/Users",
        json={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": email,
            "externalId": ext_id,
            "emails": [{"value": email, "primary": True}],
            "active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["userName"] == email
    assert body["externalId"] == ext_id
    assert body["active"] is True
    assert body["id"] == ext_id

    # GET reflects the row.
    got = scim_app.get(
        f"/scim/v2/Users/{body['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.status_code == 200, got.text
    assert got.json()["userName"] == email


@requires_postgres
def test_scim_user_patch_active_false_revokes_sessions_via_http(scim_app):
    """End-to-end: SCIM PATCH active=false revokes sessions for the user."""
    from ai_portal.auth.model import UserSession
    from ai_portal.auth.sessions import create_session
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import ScimEndpointService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-http-deact")
            ep = ScimEndpointService(db).create_endpoint(
                org_id=org_id, name="wire", preset="generic"
            )
            token = ep.token
            db.commit()
    finally:
        db.close()

    tag = secrets.token_hex(4)
    email = f"deact-http-{tag}@acme.test"
    ext_id = f"deact-http-{tag}"
    r = scim_app.post(
        "/scim/v2/Users",
        json={
            "userName": email,
            "externalId": ext_id,
            "emails": [{"value": email, "primary": True}],
            "active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    user_scim_id = r.json()["id"]

    # Plant a session for the user.
    db = SessionLocal()
    try:
        with bypass_rls(db):
            from sqlalchemy import select

            from ai_portal.auth.model import User

            user = db.scalars(
                select(User).where(User.scim_external_id == ext_id)
            ).one()
            session_row = create_session(
                db,
                user_id=user.id,
                refresh_token=secrets.token_hex(16),
                ip="127.0.0.1",
                user_agent="probe",
            )
            db.commit()
            session_id = session_row.id
    finally:
        db.close()

    # PATCH active=false.
    p = scim_app.patch(
        f"/scim/v2/Users/{user_scim_id}",
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert p.status_code == 200, p.text
    assert p.json()["active"] is False

    # Session row carries revoked_at.
    db = SessionLocal()
    try:
        with bypass_rls(db):
            row = db.get(UserSession, session_id)
            assert row is not None
            assert row.revoked_at is not None
    finally:
        db.close()


@requires_postgres
def test_scim_groups_crud_via_http(scim_app):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.scim.service import ScimEndpointService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "scim-grp-http")
            ep = ScimEndpointService(db).create_endpoint(
                org_id=org_id, name="wire", preset="generic"
            )
            token = ep.token
            db.commit()
    finally:
        db.close()

    tag = secrets.token_hex(4)
    # Create.
    r = scim_app.post(
        "/scim/v2/Groups",
        json={"displayName": f"Engineers-{tag}", "externalId": f"g-eng-{tag}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    gid = r.json()["id"]

    # List.
    lst = scim_app.get(
        "/scim/v2/Groups", headers={"Authorization": f"Bearer {token}"}
    )
    assert lst.status_code == 200
    assert any(g["id"] == gid for g in lst.json()["Resources"])

    # Delete.
    d = scim_app.delete(
        f"/scim/v2/Groups/{gid}", headers={"Authorization": f"Bearer {token}"}
    )
    assert d.status_code == 204
