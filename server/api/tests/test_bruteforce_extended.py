"""Brute-force limiter coverage for mfa/verify, password-reset, sso/callback.

Unit-level: builds a tiny FastAPI app per scope, stubs the underlying service to
avoid DB roundtrips, and asserts the limiter returns 429 once the bucket fills.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.auth.limiter import (
    LIMIT_FAILED_ATTEMPTS,
    LoginLimiter,
    get_scoped_limiter,
    mfa_verify_limiter,
    password_reset_limiter,
    sso_callback_limiter,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _reset_all() -> None:
    for s in (
        "login",
        "mfa_verify",
        "password_reset",
        "sso_callback",
    ):
        get_scoped_limiter(s).clear()


# ── scope wiring ─────────────────────────────────────────────────────────────


def test_scoped_limiters_are_isolated_per_scope():
    _reset_all()
    mfa_verify_limiter.record_failure("1.1.1.1", "u1")
    assert password_reset_limiter.check("1.1.1.1", "u1") is None
    assert sso_callback_limiter.check("1.1.1.1", "u1") is None


def test_get_scoped_limiter_returns_singleton():
    assert get_scoped_limiter("mfa_verify") is mfa_verify_limiter
    assert get_scoped_limiter("password_reset") is password_reset_limiter
    assert get_scoped_limiter("sso_callback") is sso_callback_limiter


def test_get_scoped_limiter_unknown_scope_raises():
    with pytest.raises(KeyError):
        get_scoped_limiter("nope")


def test_scoped_limiters_are_loginlimiter_instances():
    assert isinstance(mfa_verify_limiter, LoginLimiter)
    assert isinstance(password_reset_limiter, LoginLimiter)
    assert isinstance(sso_callback_limiter, LoginLimiter)


# ── MFA /auth/mfa/totp/verify ────────────────────────────────────────────────


@pytest.fixture
def mfa_app(monkeypatch):
    _reset_all()
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "test-secret-mfa-brute")
    from ai_portal.auth.deps import get_current_user, get_db
    from ai_portal.auth.model import User
    from ai_portal.auth.routes_mfa import router as mfa_router

    app = FastAPI()
    app.include_router(mfa_router)

    class _User:
        id = 4242

    def _fake_user() -> User:  # type: ignore[override]
        return _User()  # type: ignore[return-value]

    def _fake_db():
        yield object()

    # Patch MfaService so verify always raises InvalidTotpCode.
    from ai_portal.auth import routes_mfa as mod

    class _BadSvc:
        def __init__(self, _db): ...
        def verify_totp(self, **_):
            from ai_portal.auth.mfa_totp import InvalidTotpCode

            raise InvalidTotpCode()

    monkeypatch.setattr(mod, "MfaService", _BadSvc)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    return TestClient(app)


def test_mfa_verify_returns_429_after_threshold(mfa_app):
    for _ in range(LIMIT_FAILED_ATTEMPTS):
        bad = mfa_app.post("/auth/mfa/totp/verify", json={"code": "000000"})
        assert bad.status_code == 400, bad.text
    blocked = mfa_app.post("/auth/mfa/totp/verify", json={"code": "000000"})
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")
    assert int(blocked.headers["Retry-After"]) >= 1


# ── /v1/users/password-reset/* ───────────────────────────────────────────────


@pytest.fixture
def password_reset_app(monkeypatch):
    _reset_all()
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "test-secret-pwreset-brute")
    from ai_portal.auth.deps import get_db
    from ai_portal.auth.routes_control_plane import router as cp_router

    app = FastAPI()
    app.include_router(cp_router)

    def _fake_db():
        yield object()

    from ai_portal.auth import routes_control_plane as mod
    from ai_portal.auth.users_service import InvalidToken

    class _BadUserService:
        def __init__(self, _db): ...
        def request_password_reset(self, _body):
            return None

        def reset_password(self, _body):
            raise InvalidToken("nope")

    monkeypatch.setattr(mod, "UserService", _BadUserService)
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def test_password_reset_request_returns_429_after_threshold(password_reset_app):
    payload = {"email": "victim@example.com"}
    for _ in range(LIMIT_FAILED_ATTEMPTS):
        r = password_reset_app.post(
            "/v1/users/password-reset/request", json=payload
        )
        assert r.status_code == 202, r.text
    blocked = password_reset_app.post(
        "/v1/users/password-reset/request", json=payload
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_password_reset_confirm_returns_429_after_threshold(password_reset_app):
    payload = {"token": "deadbeef1234567890", "new_password": "Strong-pass-123"}
    for _ in range(LIMIT_FAILED_ATTEMPTS):
        bad = password_reset_app.post(
            "/v1/users/password-reset/confirm", json=payload
        )
        assert bad.status_code == 400, bad.text
    blocked = password_reset_app.post(
        "/v1/users/password-reset/confirm", json=payload
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


# ── /v1/auth/sso/callback/{kind} ─────────────────────────────────────────────


@pytest.fixture
def sso_app(monkeypatch):
    _reset_all()
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "test-secret-sso-brute")
    from ai_portal.auth.deps import get_db
    from ai_portal.auth.routes_sso import router as sso_router

    app = FastAPI()
    app.include_router(sso_router)

    def _fake_db():
        yield object()

    from ai_portal.auth import routes_sso as mod
    from ai_portal.auth.sso import SsoError

    async def _bad_complete(*_a, **_kw):
        raise SsoError("invalid state")

    monkeypatch.setattr(mod, "complete_sso", _bad_complete)
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def test_sso_callback_returns_429_after_threshold(sso_app):
    for _ in range(LIMIT_FAILED_ATTEMPTS):
        bad = sso_app.get(
            "/v1/auth/sso/callback/oidc",
            params={"state": "garbage", "code": "x"},
        )
        assert bad.status_code == 400, bad.text
    blocked = sso_app.get(
        "/v1/auth/sso/callback/oidc",
        params={"state": "garbage", "code": "x"},
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")
