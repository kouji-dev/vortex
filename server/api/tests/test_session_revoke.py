"""Tests for session listing + revoke endpoints.

Phase M2 of the Control Plane plan.
"""
from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient

from ai_portal.core.db.session import SessionLocal
from tests.conftest import requires_postgres


def _email() -> str:
    return f"sess-{secrets.token_hex(6)}@control.test"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "test-secret-for-sessions")
    from fastapi import FastAPI

    from ai_portal.auth.router import router as auth_router
    from ai_portal.auth.routes_mfa import router as auth_mfa_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(auth_mfa_router)
    return TestClient(app)


@requires_postgres
def test_list_sessions_returns_current_session(client):
    email = _email()
    r = client.post("/auth/register", json={"email": email, "password": "Strong-pass-123"})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]

    listed = client.get("/auth/sessions", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200, listed.text
    sessions = listed.json()["sessions"]
    assert len(sessions) >= 1
    assert any(s["current"] for s in sessions)
    for s in sessions:
        assert s["revoked_at"] is None


@requires_postgres
def test_login_creates_new_session_row(client):
    email = _email()
    client.post("/auth/register", json={"email": email, "password": "Strong-pass-123"})
    r = client.post("/auth/login", json={"email": email, "password": "Strong-pass-123"})
    assert r.status_code == 200, r.text
    second_token = r.json()["access_token"]

    listed = client.get(
        "/auth/sessions", headers={"Authorization": f"Bearer {second_token}"}
    )
    assert listed.status_code == 200
    sessions = listed.json()["sessions"]
    # Register + login => at least 2 sessions
    assert len(sessions) >= 2


@requires_postgres
def test_revoke_specific_session_marks_revoked(client):
    email = _email()
    client.post("/auth/register", json={"email": email, "password": "Strong-pass-123"})
    r = client.post("/auth/login", json={"email": email, "password": "Strong-pass-123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sessions = client.get("/auth/sessions", headers=headers).json()["sessions"]
    target = next(s for s in sessions if not s["current"])
    drop = client.delete(f"/auth/sessions/{target['id']}", headers=headers)
    assert drop.status_code == 204, drop.text

    after = client.get("/auth/sessions", headers=headers).json()["sessions"]
    by_id = {s["id"]: s for s in after}
    assert by_id[target["id"]]["revoked_at"] is not None


@requires_postgres
def test_revoke_all_keeps_current_session(client):
    email = _email()
    client.post("/auth/register", json={"email": email, "password": "Strong-pass-123"})
    client.post("/auth/login", json={"email": email, "password": "Strong-pass-123"})
    r = client.post("/auth/login", json={"email": email, "password": "Strong-pass-123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    drop = client.delete("/auth/sessions", headers=headers)
    assert drop.status_code == 204, drop.text

    after = client.get("/auth/sessions", headers=headers).json()["sessions"]
    revoked = [s for s in after if s["revoked_at"] is not None]
    active = [s for s in after if s["revoked_at"] is None]
    assert len(active) == 1
    assert active[0]["current"] is True
    assert revoked, "expected at least one revoked session"


@requires_postgres
def test_revoke_unknown_session_returns_404(client):
    email = _email()
    r = client.post("/auth/register", json={"email": email, "password": "Strong-pass-123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    drop = client.delete(
        "/auth/sessions/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert drop.status_code == 404
