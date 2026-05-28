"""POST /v1/orgs/{id}/restore — HTTP-level status code matrix."""
from __future__ import annotations

import uuid as _uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "test-secret-restore")
    from ai_portal.auth.deps import get_current_user, get_db
    from ai_portal.auth.routes_control_plane import router as cp_router

    app = FastAPI()
    app.include_router(cp_router)

    class _User:
        id = 1
        role = "owner"

    def _user():
        return _User()

    def _db():
        yield object()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    return app


def _stub_service(monkeypatch, restore_impl):
    """Replace OrgService.restore with the supplied impl."""
    from ai_portal.auth import routes_control_plane as mod

    class _Svc:
        def __init__(self, _db): ...
        def restore(self, org_id):
            return restore_impl(org_id)

    monkeypatch.setattr(mod, "OrgService", _Svc)


def test_restore_returns_200_on_success(app_client, monkeypatch):
    org_id = _uuid.uuid4()

    class _Org:
        id = org_id
        slug = "acme"
        name = "Acme"
        region = "eu-west-1"
        status = "active"
        instance_mode = False
        created_at = __import__("datetime").datetime.now(
            __import__("datetime").UTC
        )

    _stub_service(monkeypatch, lambda _id: _Org())
    client = TestClient(app_client)
    r = client.post(f"/v1/orgs/{org_id}/restore")
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "acme"


def test_restore_returns_404_when_org_missing(app_client, monkeypatch):
    from ai_portal.auth.orgs_service import OrgNotFound

    def _restore(_id):
        raise OrgNotFound("missing")

    _stub_service(monkeypatch, _restore)
    client = TestClient(app_client)
    r = client.post(f"/v1/orgs/{_uuid.uuid4()}/restore")
    assert r.status_code == 404


def test_restore_returns_409_when_not_archived(app_client, monkeypatch):
    from ai_portal.auth.orgs_service import OrgNotArchived

    def _restore(_id):
        raise OrgNotArchived("not archived")

    _stub_service(monkeypatch, _restore)
    client = TestClient(app_client)
    r = client.post(f"/v1/orgs/{_uuid.uuid4()}/restore")
    assert r.status_code == 409


def test_restore_returns_410_when_window_expired(app_client, monkeypatch):
    from ai_portal.auth.orgs_service import OrgRestoreWindowExpired

    def _restore(_id):
        raise OrgRestoreWindowExpired("expired")

    _stub_service(monkeypatch, _restore)
    client = TestClient(app_client)
    r = client.post(f"/v1/orgs/{_uuid.uuid4()}/restore")
    assert r.status_code == 410
    assert "30 days" in r.json()["detail"]


def test_restore_requires_owner_or_admin_role(app_client, monkeypatch):
    from ai_portal.auth.deps import get_current_user

    class _MemberUser:
        id = 5
        role = "member"

    app_client.dependency_overrides[get_current_user] = lambda: _MemberUser()

    def _restore(_id):
        raise AssertionError("service should not be called")

    _stub_service(monkeypatch, _restore)
    client = TestClient(app_client)
    r = client.post(f"/v1/orgs/{_uuid.uuid4()}/restore")
    assert r.status_code == 403
