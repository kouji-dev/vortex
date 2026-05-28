"""Tests for TOTP MFA — enroll, verify, login step gating.

Phase M1 of the Control Plane plan.
"""
from __future__ import annotations

import secrets

import pyotp
import pytest

from ai_portal.auth.mfa_totp import (
    InvalidTotpCode,
    MfaFactorNotFound,
    MfaService,
    TotpAlreadyEnrolled,
    user_has_confirmed_totp,
)
from ai_portal.auth.users_schemas import SignupRequest
from ai_portal.auth.users_service import UserService
from ai_portal.core.db.session import SessionLocal
from tests.conftest import requires_postgres


def _email() -> str:
    return f"mfa-{secrets.token_hex(6)}@control.test"


# ── Enroll ───────────────────────────────────────────────────────────────────


@requires_postgres
def test_enroll_returns_secret_and_provisioning_uri():
    db = SessionLocal()
    try:
        user = UserService(db).signup(SignupRequest(email=_email(), password="Strong-pass-123"))
        svc = MfaService(db)
        enrol = svc.enroll_totp(user_id=user.id, issuer="AI Portal")
        assert enrol.secret
        # Base32 secret usable with pyotp.
        totp = pyotp.TOTP(enrol.secret)
        assert totp.now()  # sanity: generates 6-digit code
        assert enrol.provisioning_uri.startswith("otpauth://totp/")
        assert "secret=" in enrol.provisioning_uri.lower()
        assert enrol.qr_code_data_uri.startswith("data:")
        # Factor row exists but is unconfirmed.
        assert user_has_confirmed_totp(db, user.id) is False
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_enroll_twice_before_confirm_replaces_pending_factor():
    db = SessionLocal()
    try:
        user = UserService(db).signup(SignupRequest(email=_email(), password="Strong-pass-123"))
        svc = MfaService(db)
        first = svc.enroll_totp(user_id=user.id)
        second = svc.enroll_totp(user_id=user.id)
        # Second enroll mints a fresh secret so QR rescans never lock the user out.
        assert first.secret != second.secret
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_enroll_after_confirm_raises_already_enrolled():
    db = SessionLocal()
    try:
        user = UserService(db).signup(SignupRequest(email=_email(), password="Strong-pass-123"))
        svc = MfaService(db)
        enrol = svc.enroll_totp(user_id=user.id)
        code = pyotp.TOTP(enrol.secret).now()
        svc.verify_totp(user_id=user.id, code=code)
        with pytest.raises(TotpAlreadyEnrolled):
            svc.enroll_totp(user_id=user.id)
    finally:
        db.rollback()
        db.close()


# ── Verify ───────────────────────────────────────────────────────────────────


@requires_postgres
def test_verify_totp_confirms_factor():
    db = SessionLocal()
    try:
        user = UserService(db).signup(SignupRequest(email=_email(), password="Strong-pass-123"))
        svc = MfaService(db)
        enrol = svc.enroll_totp(user_id=user.id)
        code = pyotp.TOTP(enrol.secret).now()
        confirmed = svc.verify_totp(user_id=user.id, code=code)
        assert confirmed is True
        assert user_has_confirmed_totp(db, user.id) is True
        # Login-time check accepts a fresh code.
        next_code = pyotp.TOTP(enrol.secret).now()
        assert svc.check_login_totp(user_id=user.id, code=next_code) is True
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_verify_totp_wrong_code_raises():
    db = SessionLocal()
    try:
        user = UserService(db).signup(SignupRequest(email=_email(), password="Strong-pass-123"))
        svc = MfaService(db)
        svc.enroll_totp(user_id=user.id)
        with pytest.raises(InvalidTotpCode):
            svc.verify_totp(user_id=user.id, code="000000")
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_check_login_totp_without_factor_raises():
    db = SessionLocal()
    try:
        user = UserService(db).signup(SignupRequest(email=_email(), password="Strong-pass-123"))
        svc = MfaService(db)
        with pytest.raises(MfaFactorNotFound):
            svc.check_login_totp(user_id=user.id, code="123456")
    finally:
        db.rollback()
        db.close()


# ── Login flow ───────────────────────────────────────────────────────────────


@requires_postgres
def test_login_blocks_when_totp_required(client_with_local_auth):
    """If user has a confirmed TOTP factor, /v1/auth/login returns a
    mfa_required response rather than tokens until totp_code is supplied."""
    client = client_with_local_auth
    email = _email()
    password = "Strong-pass-123"
    # Register and verify email so login passes the verified check (path uses dev strategy
    # which doesn't require verification, but we exercise the full flow).
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text

    # Enroll + confirm TOTP via API.
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    e = client.post("/auth/mfa/totp/enroll", headers=headers)
    assert e.status_code == 200, e.text
    secret = e.json()["secret"]
    v = client.post(
        "/auth/mfa/totp/verify",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert v.status_code == 200, v.text

    # Login without code → 401 with mfa_required flag.
    r2 = client.post("/auth/login", json={"email": email, "password": password})
    assert r2.status_code == 401, r2.text
    body = r2.json()
    assert body.get("detail", {}).get("error") == "mfa_required"

    # Login with code → 200 tokens.
    r3 = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert r3.status_code == 200, r3.text
    assert r3.json().get("access_token")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def client_with_local_auth(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "test-secret-for-mfa")
    from fastapi import FastAPI

    from ai_portal.auth.router import router as auth_router
    from ai_portal.auth.routes_mfa import router as auth_mfa_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(auth_mfa_router)
    return TestClient(app)
