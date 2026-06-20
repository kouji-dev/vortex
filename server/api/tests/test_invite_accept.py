"""Tests for POST /auth/invites/{token}/accept.

Covers:
- accept valid invite → 200, user attached to org, accepted_at set
- accept expired invite → 400
- accept revoked invite → 410
- accept already-used invite → 409
- accept unauthenticated → 401
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from ai_portal.auth.strategies.jwt import create_access_token


SECRET = "test-secret-invite-accept"


def _make_user(
    *,
    user_uuid=None,
    org_id=None,
    role: str = "member",
    is_active: bool = True,
):
    u = MagicMock(spec=["id", "uuid", "email", "role", "org_id", "is_active"])
    u.id = 1
    u.uuid = user_uuid or uuid.uuid4()
    u.email = "user@example.com"
    u.role = role
    u.org_id = org_id
    u.is_active = is_active
    return u


def _make_invite(
    *,
    token: str = "valid-token",
    org_id=None,
    role: str = "member",
    accepted_at=None,
    revoked_at=None,
    expires_at=None,
):
    inv = MagicMock()
    inv.token = token
    inv.org_id = org_id or uuid.uuid4()
    inv.role = role
    inv.accepted_at = accepted_at
    inv.revoked_at = revoked_at
    inv.expires_at = (expires_at or datetime.now(UTC) + timedelta(days=7)).replace(tzinfo=None)
    return inv


def _make_access_token(user_uuid, org_id=None):
    return create_access_token(
        user_uuid=user_uuid,
        org_id=org_id or uuid.uuid4(),
        role="member",
        secret=SECRET,
    )


def _get_client(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", SECRET)
    from fastapi.testclient import TestClient
    from ai_portal.main import app
    return TestClient(app)


# ── happy path ────────────────────────────────────────────────────────────────


class TestAcceptInviteAuthenticated:

    def test_accept_valid_invite_returns_200(self, monkeypatch):
        client = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        org_id = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid)
        invite = _make_invite(org_id=org_id, role="admin")
        access = _make_access_token(user_uuid)

        db = MagicMock()
        # First scalars call → find user by uuid; second → find invite by token
        db.scalars.return_value.first.side_effect = [user, invite]

        with patch("ai_portal.auth.router.get_db", return_value=iter([db])):
            resp = client.post(
                "/auth/invites/valid-token/accept",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["org_id"] == str(org_id)
        assert body["role"] == "admin"

    def test_accept_invite_sets_user_org_and_role(self, monkeypatch):
        client = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        org_id = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid)
        invite = _make_invite(org_id=org_id, role="admin")
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, invite]

        with patch("ai_portal.auth.router.get_db", return_value=iter([db])):
            resp = client.post(
                "/auth/invites/valid-token/accept",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert resp.status_code == 200
        # Verify the user was mutated
        assert user.org_id == org_id
        assert user.role == "admin"
        # Verify accepted_at was set
        assert invite.accepted_at is not None
        db.commit.assert_called()
        db.refresh.assert_called_with(user)

    # ── error cases ───────────────────────────────────────────────────────────

    def test_accept_unauthenticated_returns_401(self, monkeypatch):
        client = _get_client(monkeypatch)
        resp = client.post("/auth/invites/some-token/accept")
        assert resp.status_code == 401

    def test_accept_invalid_bearer_returns_401(self, monkeypatch):
        client = _get_client(monkeypatch)
        resp = client.post(
            "/auth/invites/some-token/accept",
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 401

    def test_accept_expired_invite_returns_400(self, monkeypatch):
        client = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid)
        expired = _make_invite(
            token="expired-tok",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, expired]

        with patch("ai_portal.auth.router.get_db", return_value=iter([db])):
            resp = client.post(
                "/auth/invites/expired-tok/accept",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    def test_accept_revoked_invite_returns_410(self, monkeypatch):
        client = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid)
        revoked = _make_invite(
            token="revoked-tok",
            revoked_at=datetime.now(UTC) - timedelta(hours=1),
        )
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, revoked]

        with patch("ai_portal.auth.router.get_db", return_value=iter([db])):
            resp = client.post(
                "/auth/invites/revoked-tok/accept",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert resp.status_code == 410
        assert "revoked" in resp.json()["detail"].lower()

    def test_accept_already_used_invite_returns_409(self, monkeypatch):
        client = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid)
        used = _make_invite(
            token="used-tok",
            accepted_at=datetime.now(UTC) - timedelta(hours=2),
        )
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, used]

        with patch("ai_portal.auth.router.get_db", return_value=iter([db])):
            resp = client.post(
                "/auth/invites/used-tok/accept",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert resp.status_code == 409
        assert "already used" in resp.json()["detail"].lower()

    def test_accept_nonexistent_invite_returns_404(self, monkeypatch):
        client = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid)
        access = _make_access_token(user_uuid)

        db = MagicMock()
        # First call returns user, second returns None (invite not found)
        db.scalars.return_value.first.side_effect = [user, None]

        with patch("ai_portal.auth.router.get_db", return_value=iter([db])):
            resp = client.post(
                "/auth/invites/ghost-token/accept",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert resp.status_code == 404
