from __future__ import annotations

import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from ai_portal.auth.entra import decode_entra_access_token, roles_from_claims
from ai_portal.config import get_settings
from ai_portal.main import app
from ai_portal.services.user_identity import upsert_user_from_entra_claims
from tests.conftest import requires_postgres


def test_roles_from_claims_list():
    assert roles_from_claims({"roles": ["Admin", "User"]}) == ["Admin", "User"]


def test_roles_from_claims_string():
    assert roles_from_claims({"roles": "Admin"}) == ["Admin"]


def test_roles_from_claims_empty():
    assert roles_from_claims({}) == []


def _rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _fake_jwks_client(private_key):
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    class _SK:
        def __init__(self, key_bytes: bytes):
            self.key = serialization.load_pem_public_key(key_bytes)

    class _Client:
        def get_signing_key_from_jwt(self, _token: str) -> _SK:
            return _SK(pub_pem)

    return _Client()


def test_decode_entra_access_token_ok():
    tenant = "11111111-1111-1111-1111-111111111111"
    aud = "api://test-audience"
    private_key = _rsa_key()
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "sub": "subj",
        "aud": aud,
        "exp": now + 3600,
        "iat": now,
        "tid": tenant,
        "oid": "22222222-2222-2222-2222-222222222222",
        "roles": ["User"],
        "preferred_username": "u@example.com",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    fake = _fake_jwks_client(private_key)
    out = decode_entra_access_token(
        token,
        tenant_id=tenant,
        audience=aud,
        jwks_client=fake,
    )
    assert out["oid"] == claims["oid"]


def test_decode_entra_access_token_tid_mismatch():
    tenant = "11111111-1111-1111-1111-111111111111"
    aud = "api://test-audience"
    private_key = _rsa_key()
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "sub": "subj",
        "aud": aud,
        "exp": now + 3600,
        "iat": now,
        "tid": "99999999-9999-9999-9999-999999999999",
        "oid": "22222222-2222-2222-2222-222222222222",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    fake = _fake_jwks_client(private_key)
    with pytest.raises(ValueError, match="tid"):
        decode_entra_access_token(
            token,
            tenant_id=tenant,
            audience=aud,
            jwks_client=fake,
        )


def test_upsert_user_from_entra_claims(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from ai_portal.db.base import Base
    from ai_portal.models import User

    db_path = tmp_path / "t.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        u = upsert_user_from_entra_claims(
            db,
            {
                "oid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "preferred_username": "new@example.com",
            },
        )
        db.commit()
        assert u.email == "new@example.com"
        assert u.entra_object_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        u2 = upsert_user_from_entra_claims(
            db,
            {
                "oid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "preferred_username": "new@example.com",
            },
        )
        assert u2.id == u.id
    finally:
        db.close()


client = TestClient(app)


@requires_postgres
def test_me_dev_returns_user(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    get_settings.cache_clear()
    r = client.get(
        "/api/me",
        headers={"Authorization": "Bearer devtoken"},
    )
    get_settings.cache_clear()
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" in body and body["email"] == "dev@localhost"
    assert body["roles"] == []


def test_me_missing_token():
    get_settings.cache_clear()
    r = client.get("/api/me")
    get_settings.cache_clear()
    assert r.status_code == 401


@requires_postgres
def test_admin_ping_dev_ok(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    get_settings.cache_clear()
    r = client.get(
        "/api/admin/ping",
        headers={"Authorization": "Bearer devtoken"},
    )
    get_settings.cache_clear()
    assert r.status_code == 200, r.text


@requires_postgres
def test_admin_ping_entra_forbidden_without_role(monkeypatch):
    """Entra token without Admin app role → 403 on /api/admin/ping."""
    tenant = "11111111-1111-1111-1111-111111111111"
    aud = "api://test-audience"
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_TENANT_ID", tenant)
    monkeypatch.setenv("ENTRA_API_AUDIENCE", aud)
    get_settings.cache_clear()
    private_key = _rsa_key()
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "sub": "subj",
        "aud": aud,
        "exp": now + 3600,
        "iat": now,
        "tid": tenant,
        "oid": "22222222-2222-2222-2222-222222222222",
        "roles": ["User"],
        "preferred_username": "entrauser@example.com",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    fake = _fake_jwks_client(private_key)

    with patch(
        "ai_portal.auth.entra._jwks_client",
        return_value=fake,
    ):
        r = client.get(
            "/api/admin/ping",
            headers={"Authorization": f"Bearer {token}"},
        )
    get_settings.cache_clear()
    assert r.status_code == 403
