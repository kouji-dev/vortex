"""Phase G5 — SSO start / callback + JIT user provisioning.

Covers:
- ``resolve_idp_for_login`` matches by email domain first, then by org slug.
- ``jit_provision_user`` creates a fresh user the first time; returns the
  existing row on subsequent logins.
- ``start_sso`` → ``complete_sso`` end-to-end with an OIDC provider stubbed
  via respx creates a user.
- ``/v1/auth/sso/start`` returns a redirect URL containing the IdP's
  authorize host. ``/v1/auth/sso/callback/{kind}`` validates the response,
  creates the user, and mints a session.
"""

from __future__ import annotations

import base64
import json
import uuid as _uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select, text

import ai_portal.auth.idp.providers  # noqa: F401 — register provider factories
from ai_portal.auth.idp.model import IdpConnection
from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.model import User
from ai_portal.auth.sso import (
    IdpNotFound,
    SsoError,
    complete_sso,
    jit_provision_user,
    resolve_idp_for_login,
    start_sso,
    state_cache,
)

from tests.conftest import requires_postgres


DISCOVERY_URL = "https://idp.example.com/.well-known/openid-configuration"
AUTH_EP = "https://idp.example.com/authorize"
TOKEN_EP = "https://idp.example.com/token"
REDIRECT_URI = "https://app.example.com/v1/auth/sso/callback/oidc"


def _id_token(claims: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def _mk_org(db, *, slug: str) -> _uuid.UUID:
    org_id = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'SsoCo') "
            "ON CONFLICT (slug) DO NOTHING"
        ),
        {"id": str(org_id), "slug": slug},
    )
    row = db.execute(
        text("SELECT id FROM orgs WHERE slug = :slug"), {"slug": slug}
    ).first()
    return row[0] if row else org_id


def _mk_conn(
    db,
    *,
    org_id: _uuid.UUID,
    kind: str = "oidc",
    domain: str = "",
    config: dict | None = None,
    sso_required: bool = False,
) -> IdpConnection:
    conn = IdpConnection(
        org_id=org_id,
        kind=kind,
        domain=domain,
        config_encrypted=json.dumps(
            config
            or {
                "client_id": "cid",
                "client_secret": "csecret",
                "discovery_url": DISCOVERY_URL,
            }
        ),
        enabled=True,
        sso_required=sso_required,
    )
    db.add(conn)
    db.flush()
    return conn


# ──────────────────────────────────────────────────────────────────────────
# Pure helpers
# ──────────────────────────────────────────────────────────────────────────
def test_resolve_raises_when_no_email_and_no_slug():
    with pytest.raises(IdpNotFound):
        resolve_idp_for_login(None, email=None, org_slug=None)  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────────
# resolve_idp_for_login
# ──────────────────────────────────────────────────────────────────────────
@requires_postgres
def test_resolve_by_email_domain():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"acme-{_uuid.uuid4().hex[:6]}")
            conn = _mk_conn(db, org_id=org_id, domain="acme.example")
            found = resolve_idp_for_login(
                db, email="alice@acme.example", org_slug=None
            )
            assert found.id == conn.id
            db.rollback()
    finally:
        db.close()


@requires_postgres
def test_resolve_by_org_slug_when_domain_no_match():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            slug = f"acme-{_uuid.uuid4().hex[:6]}"
            org_id = _mk_org(db, slug=slug)
            conn = _mk_conn(db, org_id=org_id, domain="")
            found = resolve_idp_for_login(
                db, email="alice@unknown.example", org_slug=slug
            )
            assert found.id == conn.id
            db.rollback()
    finally:
        db.close()


@requires_postgres
def test_resolve_raises_when_nothing_matches():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            with pytest.raises(IdpNotFound):
                resolve_idp_for_login(
                    db,
                    email="nobody@nowhere.example",
                    org_slug="missing-slug",
                )
            db.rollback()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────
# jit_provision_user
# ──────────────────────────────────────────────────────────────────────────
@requires_postgres
def test_jit_creates_new_user():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"jit-new-{_uuid.uuid4().hex[:6]}")
            conn = _mk_conn(db, org_id=org_id, domain="jit-new.example")
            email = f"new-{_uuid.uuid4().hex[:8]}@jit-new.example"
            user = jit_provision_user(
                db,
                claims=UserClaims(subject="sub-1", email=email, name="Alice"),
                conn=conn,
            )
            assert user.email == email
            assert user.org_id == org_id
            assert user.is_active is True
            assert user.is_verified is True
            assert user.name == "Alice"
            db.rollback()
    finally:
        db.close()


@requires_postgres
def test_jit_returns_existing_user_unchanged():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"jit-ret-{_uuid.uuid4().hex[:6]}")
            conn = _mk_conn(db, org_id=org_id, domain="jit-ret.example")
            email = f"ret-{_uuid.uuid4().hex[:8]}@jit-ret.example"
            first = jit_provision_user(
                db,
                claims=UserClaims(subject="s", email=email),
                conn=conn,
            )
            again = jit_provision_user(
                db,
                claims=UserClaims(subject="s", email=email),
                conn=conn,
            )
            assert again.id == first.id
            db.rollback()
    finally:
        db.close()


@requires_postgres
def test_jit_rejects_disabled_user():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, slug=f"jit-dis-{_uuid.uuid4().hex[:6]}")
            conn = _mk_conn(db, org_id=org_id, domain="jit-dis.example")
            email = f"dis-{_uuid.uuid4().hex[:8]}@jit-dis.example"
            user = User(
                email=email,
                uuid=_uuid.uuid4(),
                org_id=org_id,
                is_active=False,
                is_verified=False,
            )
            db.add(user)
            db.flush()
            with pytest.raises(SsoError, match="disabled"):
                jit_provision_user(
                    db,
                    claims=UserClaims(subject="s", email=email),
                    conn=conn,
                )
            db.rollback()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────
# start_sso / complete_sso end-to-end (OIDC via respx)
# ──────────────────────────────────────────────────────────────────────────
@requires_postgres
@pytest.mark.asyncio
async def test_start_sso_returns_authorize_redirect(respx_mock):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": AUTH_EP,
                "token_endpoint": TOKEN_EP,
            },
        )
    )
    db = SessionLocal()
    try:
        with bypass_rls(db):
            domain = f"sso-start-{_uuid.uuid4().hex[:6]}.example"
            org_id = _mk_org(db, slug=f"sso-start-{_uuid.uuid4().hex[:6]}")
            _mk_conn(db, org_id=org_id, domain=domain)

            result = await start_sso(
                db,
                email=f"alice@{domain}",
                org_slug=None,
                redirect_uri=REDIRECT_URI,
            )
            parsed = urlparse(result.redirect_url)
            assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTH_EP
            qs = parse_qs(parsed.query)
            assert qs["code_challenge_method"] == ["S256"]
            assert qs["state"] == [result.state]
            db.rollback()
    finally:
        db.close()


@requires_postgres
@pytest.mark.asyncio
async def test_complete_sso_jit_provisions_user(respx_mock):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": AUTH_EP,
                "token_endpoint": TOKEN_EP,
            },
        )
    )
    state_cache().clear()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            domain = f"sso-cb-{_uuid.uuid4().hex[:6]}.example"
            org_id = _mk_org(db, slug=f"sso-cb-{_uuid.uuid4().hex[:6]}")
            _mk_conn(db, org_id=org_id, domain=domain)
            email = f"alice-{_uuid.uuid4().hex[:6]}@{domain}"

            start = await start_sso(
                db,
                email=email,
                org_slug=None,
                redirect_uri=REDIRECT_URI,
            )

            id_token = _id_token(
                {"sub": "idp-user-1", "email": email, "name": "Alice"}
            )
            respx_mock.post(TOKEN_EP).mock(
                return_value=httpx.Response(
                    200,
                    json={"id_token": id_token, "token_type": "Bearer"},
                )
            )

            result = await complete_sso(
                db,
                state=start.state,
                params={"code": "auth-code", "state": start.state},
            )
            assert result.user.email == email
            assert result.user.org_id == org_id
            assert result.user.is_verified is True
            assert result.claims.subject == "idp-user-1"
            db.rollback()
    finally:
        db.close()


@requires_postgres
@pytest.mark.asyncio
async def test_complete_sso_rejects_unknown_state():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            with pytest.raises(SsoError, match="unknown"):
                await complete_sso(
                    db,
                    state="never-issued",
                    params={"code": "c", "state": "never-issued"},
                )
            db.rollback()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────
# HTTP routes
# ──────────────────────────────────────────────────────────────────────────
def _http_client():
    from fastapi.testclient import TestClient

    from ai_portal.main import app

    return TestClient(app, follow_redirects=False)


@requires_postgres
def test_sso_start_route_redirects_to_authorize(respx_mock):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": AUTH_EP,
                "token_endpoint": TOKEN_EP,
            },
        )
    )
    state_cache().clear()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            domain = f"route-start-{_uuid.uuid4().hex[:6]}.example"
            org_id = _mk_org(db, slug=f"route-start-{_uuid.uuid4().hex[:6]}")
            _mk_conn(db, org_id=org_id, domain=domain)
            db.commit()
    finally:
        db.close()

    client = _http_client()
    resp = client.post(
        "/v1/auth/sso/start",
        json={"email": f"alice@{domain}"},
    )
    assert resp.status_code == 302, resp.text
    assert resp.headers["location"].startswith(AUTH_EP)


@requires_postgres
def test_sso_start_route_404_when_no_idp():
    client = _http_client()
    resp = client.post(
        "/v1/auth/sso/start",
        json={"email": "nobody@no-idp-anywhere.example"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"] == "idp_not_found"


@requires_postgres
def test_sso_callback_route_creates_user_and_session(respx_mock):
    """Drive the full HTTP flow: /sso/start → IdP → /sso/callback → tokens."""
    from ai_portal.auth.sessions import list_sessions
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": AUTH_EP,
                "token_endpoint": TOKEN_EP,
            },
        )
    )
    state_cache().clear()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            domain = f"route-cb-{_uuid.uuid4().hex[:6]}.example"
            org_id = _mk_org(db, slug=f"route-cb-{_uuid.uuid4().hex[:6]}")
            _mk_conn(db, org_id=org_id, domain=domain)
            db.commit()
            email = f"alice-{_uuid.uuid4().hex[:6]}@{domain}"
    finally:
        db.close()

    client = _http_client()
    start_resp = client.post(
        "/v1/auth/sso/start",
        json={"email": email},
    )
    assert start_resp.status_code == 302, start_resp.text
    location = start_resp.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    id_token = _id_token({"sub": "idp-user-2", "email": email, "name": "Alice"})
    respx_mock.post(TOKEN_EP).mock(
        return_value=httpx.Response(
            200, json={"id_token": id_token, "token_type": "Bearer"}
        )
    )

    cb_resp = client.get(
        "/v1/auth/sso/callback/oidc",
        params={"code": "auth-code", "state": state},
    )
    assert cb_resp.status_code == 200, cb_resp.text
    body = cb_resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    db = SessionLocal()
    try:
        with bypass_rls(db):
            user_row = db.scalars(select(User).where(User.email == email)).first()
            assert user_row is not None
            sessions = list_sessions(db, user_id=user_row.id)
            assert len(sessions) >= 1
    finally:
        db.close()
