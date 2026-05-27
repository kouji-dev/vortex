"""Smoke tests for the control-plane router — assert routes are registered
and authenticated endpoints reject anonymous traffic.

Behavioral DB-backed tests live in test_users_service / test_orgs_service.
"""
from __future__ import annotations

import secrets
import uuid as _uuid

from fastapi.testclient import TestClient

from ai_portal.main import app

client = TestClient(app)


# ── Route registration (no DB needed) ────────────────────────────────────────


def test_signup_route_registered():
    paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/v1/users/signup" in paths
    assert "/v1/users/verify-email" in paths
    assert "/v1/users/password-reset/request" in paths
    assert "/v1/users/password-reset/confirm" in paths
    assert "/v1/users/me" in paths


def test_orgs_v1_routes_registered():
    paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/v1/orgs" in paths
    assert "/v1/orgs/{org_id}" in paths
    assert "/v1/orgs/{org_id}/invitations" in paths
    assert "/v1/orgs/{org_id}/members" in paths


def test_signup_validates_payload():
    # Missing password.
    r = client.post("/v1/users/signup", json={"email": "x@y.z"})
    assert r.status_code == 422


def test_password_reset_request_route_wired():
    # Route exists and accepts JSON. With DB available it returns 202; without
    # DB / unmigrated DB the endpoint can 5xx — both confirm the route is wired.
    r = client.post(
        "/v1/users/password-reset/request",
        json={"email": f"nobody-{secrets.token_hex(4)}@no.where"},
    )
    assert r.status_code != 404
    assert r.status_code != 422


def test_orgs_v1_endpoints_require_auth():
    org_id = _uuid.uuid4()
    # No bearer → 401 from the auth dep.
    assert client.get(f"/v1/orgs/{org_id}").status_code == 401
    assert (
        client.get(f"/v1/orgs/{org_id}/members").status_code == 401
    )
    assert (
        client.post(
            f"/v1/orgs/{org_id}/invitations",
            json={"email": "x@y.z", "role": "member"},
        ).status_code
        == 401
    )


def test_get_my_profile_requires_auth():
    assert client.get("/v1/users/me").status_code == 401
    assert (
        client.patch("/v1/users/me", json={"name": "X"}).status_code == 401
    )


