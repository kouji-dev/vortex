"""Phase G6 — org-level ``sso_required`` enforcement on password login.

Behaviour:
- ``is_sso_required(org_id)`` returns True if either:
  - ``org_settings`` has ``auth.sso_required = true``, OR
  - any enabled :class:`IdpConnection` for the org carries ``sso_required=true``.
- POST ``/auth/login`` for a user whose org enforces SSO → 403 with body
  ``{"error": "sso_required"}``.
- A user belonging to an org WITHOUT the flag still logs in normally.
"""

from __future__ import annotations

import json
import uuid as _uuid

import pytest
from sqlalchemy import text

from ai_portal.auth.idp.model import IdpConnection
from ai_portal.auth.sso import ORG_SETTING_SSO_REQUIRED, is_sso_required

from tests.conftest import requires_postgres


def _mk_org(db, *, slug: str) -> _uuid.UUID:
    org_id = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'SsoReqCo') "
            "ON CONFLICT (slug) DO NOTHING"
        ),
        {"id": str(org_id), "slug": slug},
    )
    row = db.execute(
        text("SELECT id FROM orgs WHERE slug = :slug"), {"slug": slug}
    ).first()
    return row[0] if row else org_id


def _mk_conn(db, *, org_id, sso_required=False, domain=""):
    conn = IdpConnection(
        org_id=org_id,
        kind="oidc",
        domain=domain,
        config_encrypted=json.dumps({"client_id": "c", "discovery_url": "https://x/.well-known/openid-configuration"}),
        enabled=True,
        sso_required=sso_required,
    )
    db.add(conn)
    db.flush()
    return conn


# ──────────────────────────────────────────────────────────────────────────
# is_sso_required policy resolver
# ──────────────────────────────────────────────────────────────────────────
@requires_postgres
def test_is_sso_required_false_by_default():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"req-default-{_uuid.uuid4().hex[:6]}")
            assert is_sso_required(db, org_id=org_id) is False
            db.rollback()
    finally:
        db.close()


@requires_postgres
def test_is_sso_required_true_when_org_setting_set():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.settings.service import set_org_setting

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"req-setting-{_uuid.uuid4().hex[:6]}")
            db.commit()
        set_org_setting(
            db, org_id=org_id, key=ORG_SETTING_SSO_REQUIRED, value=True
        )
        with bypass_rls(db):
            assert is_sso_required(db, org_id=org_id) is True
            # Cleanup
            db.execute(
                text("DELETE FROM org_settings WHERE org_id = :id"),
                {"id": str(org_id)},
            )
            db.execute(text("DELETE FROM orgs WHERE id = :id"), {"id": str(org_id)})
            db.commit()
    finally:
        db.close()


@requires_postgres
def test_is_sso_required_true_when_idp_connection_flag():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"req-conn-{_uuid.uuid4().hex[:6]}")
            _mk_conn(db, org_id=org_id, sso_required=True)
            db.flush()
            assert is_sso_required(db, org_id=org_id) is True
            db.rollback()
    finally:
        db.close()


@requires_postgres
def test_is_sso_required_false_when_idp_connection_disabled():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"req-dis-{_uuid.uuid4().hex[:6]}")
            conn = _mk_conn(db, org_id=org_id, sso_required=True)
            conn.enabled = False
            db.flush()
            assert is_sso_required(db, org_id=org_id) is False
            db.rollback()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────
# /auth/login enforcement
# ──────────────────────────────────────────────────────────────────────────
def _http_client():
    from fastapi.testclient import TestClient

    from ai_portal.main import app

    return TestClient(app)


@requires_postgres
def test_password_login_blocked_when_sso_required():
    from ai_portal.auth.password import hash_password
    from ai_portal.auth.model import User
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"req-block-{_uuid.uuid4().hex[:6]}")
            _mk_conn(db, org_id=org_id, sso_required=True)
            email = f"blocked-{_uuid.uuid4().hex[:8]}@req-block.example"
            user = User(
                email=email,
                hashed_password=hash_password("Strong-pass-123"),
                uuid=_uuid.uuid4(),
                org_id=org_id,
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

    client = _http_client()
    resp = client.post(
        "/auth/login",
        json={"email": email, "password": "Strong-pass-123"},
    )
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"]
    if isinstance(detail, dict):
        assert detail.get("error") == "sso_required"
    else:
        assert "sso_required" in detail


@requires_postgres
def test_password_login_succeeds_when_sso_not_required():
    from ai_portal.auth.password import hash_password
    from ai_portal.auth.model import User
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"req-ok-{_uuid.uuid4().hex[:6]}")
            # NB: no IdP connection, no setting → policy is off.
            email = f"ok-{_uuid.uuid4().hex[:8]}@req-ok.example"
            user = User(
                email=email,
                hashed_password=hash_password("Strong-pass-123"),
                uuid=_uuid.uuid4(),
                org_id=org_id,
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

    client = _http_client()
    resp = client.post(
        "/auth/login",
        json={"email": email, "password": "Strong-pass-123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
