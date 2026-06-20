"""Tests for POST /auth/invites/{token}/accept.

Covers:
- accept valid invite → 200, user attached to org, accepted_at set
- accept expired invite → 400
- accept revoked invite → 410
- accept already-used invite → 409
- accept unauthenticated → 401
- accept invite for different email → 403
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from ai_portal.auth.strategies.jwt import create_access_token


SECRET = "test-secret-invite-accept"


def _make_user(
    *,
    user_uuid=None,
    email: str = "user@example.com",
    org_id=None,
    role: str = "member",
    is_active: bool = True,
):
    u = MagicMock(spec=["id", "uuid", "email", "role", "org_id", "is_active"])
    u.id = 1
    u.uuid = user_uuid or uuid.uuid4()
    u.email = email
    u.role = role
    u.org_id = org_id
    u.is_active = is_active
    return u


def _make_invite(
    *,
    token: str = "valid-token",
    org_id=None,
    role: str = "member",
    invited_email: str = "user@example.com",
    accepted_at=None,
    revoked_at=None,
    expires_at=None,
):
    inv = MagicMock()
    inv.token = token
    inv.org_id = org_id or uuid.uuid4()
    inv.role = role
    inv.invited_email = invited_email
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
    return TestClient(app), app


def _override_db(db):
    def _gen():
        yield db
    return _gen


# ── happy path ────────────────────────────────────────────────────────────────


class TestAcceptInviteAuthenticated:

    def test_accept_valid_invite_returns_200(self, monkeypatch):
        from ai_portal.auth.deps import get_db
        client, app = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        org_id = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid, email="user@example.com")
        invite = _make_invite(org_id=org_id, role="admin", invited_email="user@example.com")
        access = _make_access_token(user_uuid)

        db = MagicMock()
        # First scalars call → find user by uuid; second → find invite by token
        db.scalars.return_value.first.side_effect = [user, invite]

        app.dependency_overrides[get_db] = _override_db(db)
        try:
            resp = client.post(
                "/auth/invites/valid-token/accept",
                headers={"Authorization": f"Bearer {access}"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["org_id"] == str(org_id)
        assert body["role"] == "admin"

    def test_accept_invite_sets_user_org_and_role(self, monkeypatch):
        from ai_portal.auth.deps import get_db
        client, app = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        org_id = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid, email="user@example.com")
        invite = _make_invite(org_id=org_id, role="admin", invited_email="user@example.com")
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, invite]

        app.dependency_overrides[get_db] = _override_db(db)
        try:
            resp = client.post(
                "/auth/invites/valid-token/accept",
                headers={"Authorization": f"Bearer {access}"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

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
        client, _ = _get_client(monkeypatch)
        resp = client.post("/auth/invites/some-token/accept")
        assert resp.status_code == 401

    def test_accept_invalid_bearer_returns_401(self, monkeypatch):
        client, _ = _get_client(monkeypatch)
        resp = client.post(
            "/auth/invites/some-token/accept",
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 401

    def test_accept_expired_invite_returns_400(self, monkeypatch):
        from ai_portal.auth.deps import get_db
        client, app = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid, email="user@example.com")
        expired = _make_invite(
            token="expired-tok",
            invited_email="user@example.com",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, expired]

        app.dependency_overrides[get_db] = _override_db(db)
        try:
            resp = client.post(
                "/auth/invites/expired-tok/accept",
                headers={"Authorization": f"Bearer {access}"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    def test_accept_revoked_invite_returns_410(self, monkeypatch):
        from ai_portal.auth.deps import get_db
        client, app = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid, email="user@example.com")
        revoked = _make_invite(
            token="revoked-tok",
            invited_email="user@example.com",
            revoked_at=datetime.now(UTC) - timedelta(hours=1),
        )
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, revoked]

        app.dependency_overrides[get_db] = _override_db(db)
        try:
            resp = client.post(
                "/auth/invites/revoked-tok/accept",
                headers={"Authorization": f"Bearer {access}"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 410
        assert "revoked" in resp.json()["detail"].lower()

    def test_accept_already_used_invite_returns_409(self, monkeypatch):
        from ai_portal.auth.deps import get_db
        client, app = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid, email="user@example.com")
        used = _make_invite(
            token="used-tok",
            invited_email="user@example.com",
            accepted_at=datetime.now(UTC) - timedelta(hours=2),
        )
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, used]

        app.dependency_overrides[get_db] = _override_db(db)
        try:
            resp = client.post(
                "/auth/invites/used-tok/accept",
                headers={"Authorization": f"Bearer {access}"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 409
        assert "already used" in resp.json()["detail"].lower()

    def test_accept_nonexistent_invite_returns_404(self, monkeypatch):
        from ai_portal.auth.deps import get_db
        client, app = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        user = _make_user(user_uuid=user_uuid, email="user@example.com")
        access = _make_access_token(user_uuid)

        db = MagicMock()
        # First call returns user, second returns None (invite not found)
        db.scalars.return_value.first.side_effect = [user, None]

        app.dependency_overrides[get_db] = _override_db(db)
        try:
            resp = client.post(
                "/auth/invites/ghost-token/accept",
                headers={"Authorization": f"Bearer {access}"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404

    def test_accept_invite_wrong_email_returns_403(self, monkeypatch):
        """Invite addressed to a different email → 403 Forbidden."""
        from ai_portal.auth.deps import get_db
        client, app = _get_client(monkeypatch)
        user_uuid = uuid.uuid4()
        # Authenticated user has one email, invite is for a different one
        user = _make_user(user_uuid=user_uuid, email="attacker@evil.com")
        invite = _make_invite(
            token="victim-tok",
            invited_email="victim@example.com",
        )
        access = _make_access_token(user_uuid)

        db = MagicMock()
        db.scalars.return_value.first.side_effect = [user, invite]

        app.dependency_overrides[get_db] = _override_db(db)
        try:
            resp = client.post(
                "/auth/invites/victim-tok/accept",
                headers={"Authorization": f"Bearer {access}"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 403
        assert "different email" in resp.json()["detail"].lower()
