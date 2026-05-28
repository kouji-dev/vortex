"""Tests for /auth/login brute-force limiter (Phase M3)."""
from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient

from ai_portal.auth.limiter import (
    LIMIT_FAILED_ATTEMPTS,
    WINDOW_SECONDS,
    LoginLimiter,
    login_limiter,
)
from tests.conftest import requires_postgres


# ── Unit tests for the limiter ───────────────────────────────────────────────


def test_limiter_allows_below_threshold():
    lim = LoginLimiter(limit=3, window_seconds=60, clock=lambda: 100.0)
    lim.record_failure("1.2.3.4", "a@b.com")
    lim.record_failure("1.2.3.4", "a@b.com")
    assert lim.check("1.2.3.4", "a@b.com") is None


def test_limiter_blocks_at_threshold():
    t = [100.0]
    lim = LoginLimiter(limit=3, window_seconds=60, clock=lambda: t[0])
    for _ in range(3):
        lim.record_failure("1.2.3.4", "a@b.com")
    retry = lim.check("1.2.3.4", "a@b.com")
    assert retry is not None
    assert 1 <= retry <= 60


def test_limiter_window_evicts_old_failures():
    t = [0.0]
    lim = LoginLimiter(limit=3, window_seconds=60, clock=lambda: t[0])
    for _ in range(3):
        lim.record_failure("1.2.3.4", "a@b.com")
    assert lim.check("1.2.3.4", "a@b.com") is not None
    t[0] = 61.0
    # All entries older than 60s — bucket clears on next check.
    assert lim.check("1.2.3.4", "a@b.com") is None


def test_limiter_success_resets_bucket():
    lim = LoginLimiter(limit=2, window_seconds=60, clock=lambda: 100.0)
    lim.record_failure("1.2.3.4", "a@b.com")
    lim.record_failure("1.2.3.4", "a@b.com")
    assert lim.check("1.2.3.4", "a@b.com") is not None
    lim.record_success("1.2.3.4", "a@b.com")
    assert lim.check("1.2.3.4", "a@b.com") is None


def test_limiter_keyed_by_ip_and_email_pair():
    lim = LoginLimiter(limit=2, window_seconds=60, clock=lambda: 100.0)
    lim.record_failure("1.2.3.4", "a@b.com")
    lim.record_failure("1.2.3.4", "a@b.com")
    # Other email same IP unaffected.
    assert lim.check("1.2.3.4", "c@d.com") is None
    # Other IP same email unaffected.
    assert lim.check("9.9.9.9", "a@b.com") is None


def test_module_singleton_has_expected_defaults():
    assert login_limiter._limit == LIMIT_FAILED_ATTEMPTS
    assert login_limiter._window == WINDOW_SECONDS


# ── Endpoint integration ─────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "test-secret-for-brute")
    from fastapi import FastAPI

    from ai_portal.auth.router import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)

    # Reset state between tests so the singleton doesn't bleed across cases.
    login_limiter.clear()
    return TestClient(app)


@requires_postgres
def test_login_returns_429_after_threshold(client):
    email = f"brute-{secrets.token_hex(6)}@control.test"
    r = client.post("/auth/register", json={"email": email, "password": "Strong-pass-123"})
    assert r.status_code == 201
    for _ in range(LIMIT_FAILED_ATTEMPTS):
        bad = client.post("/auth/login", json={"email": email, "password": "WRONG"})
        assert bad.status_code == 401, bad.text
    blocked = client.post(
        "/auth/login", json={"email": email, "password": "Strong-pass-123"}
    )
    assert blocked.status_code == 429, blocked.text
    assert blocked.headers.get("Retry-After")
    # Even with right password, the window must hold.
    assert int(blocked.headers["Retry-After"]) >= 1


@requires_postgres
def test_login_success_resets_counter(client):
    email = f"brute-{secrets.token_hex(6)}@control.test"
    client.post("/auth/register", json={"email": email, "password": "Strong-pass-123"})
    for _ in range(LIMIT_FAILED_ATTEMPTS - 1):
        client.post("/auth/login", json={"email": email, "password": "WRONG"})
    ok = client.post(
        "/auth/login", json={"email": email, "password": "Strong-pass-123"}
    )
    assert ok.status_code == 200, ok.text
    # Bucket cleared — more failures should be allowed again.
    for _ in range(LIMIT_FAILED_ATTEMPTS - 1):
        bad = client.post("/auth/login", json={"email": email, "password": "WRONG"})
        assert bad.status_code == 401
