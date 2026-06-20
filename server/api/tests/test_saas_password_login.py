"""Tests for SaaS password register + login.

Covers:
- register success → returns access_token + refresh_token
- register duplicate email → 409
- login success → returns access_token + refresh_token + verifiable JWT
- login wrong password → 401
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jwt
import pytest

from ai_portal.auth.strategies.jwt import decode_token, ALGORITHM


# ── helpers ───────────────────────────────────────────────────────────────────

SECRET = "test-secret-key-password-login"


def _make_user(
    *,
    email: str = "user@example.com",
    role: str = "owner",
    org_id=None,
    is_active: bool = True,
    is_verified: bool = False,
    is_superuser: bool = False,
):
    from ai_portal.auth.password import hash_password

    u = MagicMock()
    u.id = 1
    u.uuid = uuid.uuid4()
    u.email = email
    u.role = role
    u.org_id = org_id or uuid.uuid4()
    u.is_active = is_active
    u.is_verified = is_verified
    u.is_superuser = is_superuser
    u.hashed_password = hash_password("Passw0rd!")
    u.name = None
    return u


# ── register endpoint ─────────────────────────────────────────────────────────


class TestRegisterEndpoint:
    """POST /auth/register"""

    def _client(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
        monkeypatch.setenv("SECRET_KEY", SECRET)
        from fastapi.testclient import TestClient
        from ai_portal.main import app
        return TestClient(app)

    def test_register_success_returns_token_bundle(self, monkeypatch):
        client = self._client(monkeypatch)
        user = _make_user()
        with (
            patch("ai_portal.auth.router.UserManager") as MockManager,
            patch("ai_portal.auth.router.create_session"),
        ):
            mgr = MagicMock()
            MockManager.return_value = mgr
            mgr.register.return_value = user
            mgr.create_tokens.return_value = {
                "access_token": "acc.tok",
                "refresh_token": "ref.tok",
                "token_type": "bearer",
            }
            resp = client.post(
                "/auth/register",
                json={"email": "new@example.com", "password": "Passw0rd!"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_register_duplicate_email_returns_409(self, monkeypatch):
        client = self._client(monkeypatch)
        from ai_portal.auth.strategies.dev import RegistrationError

        with patch("ai_portal.auth.router.UserManager") as MockManager:
            mgr = MagicMock()
            MockManager.return_value = mgr
            mgr.register.side_effect = RegistrationError("Email already registered")
            resp = client.post(
                "/auth/register",
                json={"email": "dup@example.com", "password": "Passw0rd!"},
            )
        assert resp.status_code == 409

    def test_register_in_selfhosted_mode_returns_403(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "selfhosted")
        monkeypatch.setenv("SECRET_KEY", SECRET)
        from fastapi.testclient import TestClient
        from ai_portal.main import app
        client = TestClient(app)
        resp = client.post(
            "/auth/register",
            json={"email": "x@example.com", "password": "Passw0rd!"},
        )
        assert resp.status_code == 403

    def test_register_in_selfhosted_mode_blocks_open_signup(self, monkeypatch):
        # enterprise was never a valid mode; selfhosted is the correct non-saas literal
        monkeypatch.setenv("DEPLOYMENT_MODE", "selfhosted")
        monkeypatch.setenv("SECRET_KEY", SECRET)
        from fastapi.testclient import TestClient
        from ai_portal.main import app
        client = TestClient(app)
        resp = client.post(
            "/auth/register",
            json={"email": "x@example.com", "password": "Passw0rd!"},
        )
        assert resp.status_code == 403


# ── login endpoint ────────────────────────────────────────────────────────────


class TestLoginEndpoint:
    """POST /auth/login"""

    def _client(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
        monkeypatch.setenv("SECRET_KEY", SECRET)
        from fastapi.testclient import TestClient
        from ai_portal.main import app
        return TestClient(app)

    def test_login_success_returns_token_bundle(self, monkeypatch):
        client = self._client(monkeypatch)
        user = _make_user()
        with (
            patch("ai_portal.auth.router.UserManager") as MockManager,
            patch("ai_portal.auth.router.create_session"),
            patch("ai_portal.auth.router.login_limiter") as mock_limiter,
        ):
            mock_limiter.check.return_value = None
            mgr = MagicMock()
            MockManager.return_value = mgr
            mgr.authenticate.return_value = user
            mgr.create_tokens.return_value = {
                "access_token": "acc.tok",
                "refresh_token": "ref.tok",
                "token_type": "bearer",
            }
            resp = client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "Passw0rd!"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password_returns_401(self, monkeypatch):
        client = self._client(monkeypatch)
        from ai_portal.auth.strategies.dev import AuthenticationError

        with (
            patch("ai_portal.auth.router.UserManager") as MockManager,
            patch("ai_portal.auth.router.login_limiter") as mock_limiter,
        ):
            mock_limiter.check.return_value = None
            mgr = MagicMock()
            MockManager.return_value = mgr
            mgr.authenticate.side_effect = AuthenticationError("Invalid email or password")
            resp = client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "wrongpass"},
            )
        assert resp.status_code == 401

    def test_login_rate_limited_returns_429(self, monkeypatch):
        client = self._client(monkeypatch)
        with patch("ai_portal.auth.router.login_limiter") as mock_limiter:
            mock_limiter.check.return_value = 30  # 30 seconds retry-after
            resp = client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "Passw0rd!"},
            )
        assert resp.status_code == 429

    def test_login_token_is_decodable(self, monkeypatch):
        """Verify the returned JWT contains expected claims."""
        client = self._client(monkeypatch)
        user_uuid = uuid.uuid4()
        org_id = uuid.uuid4()
        user = _make_user(org_id=org_id)
        user.uuid = user_uuid

        # Real token creation (not mocked) — verifies end-to-end shape.
        from ai_portal.auth.strategies.jwt import create_access_token, create_refresh_token

        access = create_access_token(
            user_uuid=user_uuid, org_id=org_id, role="owner", secret=SECRET
        )
        refresh = create_refresh_token(
            user_uuid=user_uuid, org_id=org_id, role="owner", secret=SECRET
        )

        with (
            patch("ai_portal.auth.router.UserManager") as MockManager,
            patch("ai_portal.auth.router.create_session"),
            patch("ai_portal.auth.router.login_limiter") as mock_limiter,
        ):
            mock_limiter.check.return_value = None
            mgr = MagicMock()
            MockManager.return_value = mgr
            mgr.authenticate.return_value = user
            mgr.create_tokens.return_value = {
                "access_token": access,
                "refresh_token": refresh,
                "token_type": "bearer",
            }
            resp = client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "Passw0rd!"},
            )
        assert resp.status_code == 200
        body = resp.json()

        access_payload = decode_token(body["access_token"], secret=SECRET)
        assert access_payload["sub"] == str(user_uuid)
        assert access_payload["type"] == "access"
        assert access_payload["org_id"] == str(org_id)

        refresh_payload = decode_token(body["refresh_token"], secret=SECRET)
        assert refresh_payload["sub"] == str(user_uuid)
        assert refresh_payload["type"] == "refresh"
