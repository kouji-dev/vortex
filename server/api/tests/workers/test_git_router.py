"""Tests for /v1/workers/git-integrations endpoints.

Network is fully stubbed — monkeypatches ``_github_get`` so no real GitHub
calls are made.  Service layer functions are also monkeypatched to avoid
real SQLAlchemy / Postgres interactions.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.workers.git.router import router as git_router


# ---------------------------------------------------------------------------
# Shared canned data
# ---------------------------------------------------------------------------

_USER_UUID = uuid.uuid4()
_ORG_UUID = uuid.uuid4()
_INTEGRATION_UUID = uuid.uuid4()
_REPO1_UUID = uuid.uuid4()
_REPO2_UUID = uuid.uuid4()

_CANNED_USER_RESP = {"login": "octocat"}
_CANNED_REPOS_RESP = [
    {"full_name": "octocat/Hello-World", "default_branch": "main"},
    {"full_name": "octocat/Spoon-Knife", "default_branch": "master"},
]


# ---------------------------------------------------------------------------
# Fake model objects (with real UUIDs so str(id) is valid)
# ---------------------------------------------------------------------------


class _FakeRepo:
    def __init__(self, *, iid, full_name, default_branch="main", enabled=False):
        self.id = uuid.uuid4()
        self.integration_id = iid
        self.full_name = full_name
        self.default_branch = default_branch
        self.enabled = enabled


class _FakeIntegration:
    def __init__(self):
        self.id = _INTEGRATION_UUID
        self.user_id = _USER_UUID
        self.org_id = None
        self.kind = "github"
        self.account_login = "octocat"
        self.auth_type = "token"
        self.enabled = True
        self.config_encrypted = b""


def _make_repos(integration_id=_INTEGRATION_UUID):
    return [
        _FakeRepo(iid=integration_id, full_name="octocat/Hello-World", default_branch="main"),
        _FakeRepo(iid=integration_id, full_name="octocat/Spoon-Knife", default_branch="master"),
    ]


# ---------------------------------------------------------------------------
# Fake auth user + DB stub (no SQL needed)
# ---------------------------------------------------------------------------


class _FakeUser:
    id = 1
    uuid = _USER_UUID
    org_id = _ORG_UUID


class _FakeDb:
    """Null DB — service calls are monkeypatched so these methods aren't hit."""

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        pass


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(git_router)

    fake_db = _FakeDb()
    fake_user = _FakeUser()

    def _get_db():
        yield fake_db

    def _get_user():
        return fake_user

    def _get_org_id():
        return _ORG_UUID

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    app.dependency_overrides[get_current_org_id] = _get_org_id
    return app


@pytest.fixture()
def app():
    return _make_app()


@pytest.fixture()
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# httpx Response helper
# ---------------------------------------------------------------------------


def _make_gh_response(status_code: int, data):
    import httpx
    return httpx.Response(status_code, json=data)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_returns_integration_and_repos(monkeypatch):
    """POST with valid token → 201, account_login==octocat, 2 repos, no token field."""
    import ai_portal.workers.git.connection_service as conn_svc

    fake_integration = _FakeIntegration()
    fake_repos = _make_repos()

    async def _fake_github_get(token: str, path: str):
        if path == "/user":
            return _make_gh_response(200, _CANNED_USER_RESP)
        return _make_gh_response(200, _CANNED_REPOS_RESP)

    monkeypatch.setattr(conn_svc, "_github_get", _fake_github_get)

    async def _fake_connect(db, *, owner_user_id, org_id, token):
        return fake_integration

    monkeypatch.setattr(conn_svc, "connect_github", _fake_connect)

    def _fake_list_repos(db, integration_id):
        return fake_repos

    monkeypatch.setattr(conn_svc, "list_repos", _fake_list_repos)

    app = _make_app()
    client = TestClient(app)

    resp = client.post(
        "/v1/workers/git-integrations",
        json={"kind": "github", "scope": "user", "token": "ghp_x"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["account_login"] == "octocat"
    assert len(body["repos"]) == 2
    repo_names = {r["full_name"] for r in body["repos"]}
    assert "octocat/Hello-World" in repo_names
    assert "octocat/Spoon-Knife" in repo_names

    # No token or config_encrypted field anywhere in the serialised output.
    assert "token" not in body
    assert "config_encrypted" not in body
    for r in body["repos"]:
        assert "token" not in r


@pytest.mark.asyncio
async def test_connect_bad_token_returns_400(monkeypatch):
    """POST with rejected token → 400."""
    import ai_portal.workers.git.connection_service as conn_svc

    async def _fake_github_get(token: str, path: str):
        return _make_gh_response(401, {"message": "Bad credentials"})

    monkeypatch.setattr(conn_svc, "_github_get", _fake_github_get)

    async def _fake_connect(db, *, owner_user_id, org_id, token):
        raise conn_svc.InvalidGitToken("GitHub token rejected (HTTP 401)")

    monkeypatch.setattr(conn_svc, "connect_github", _fake_connect)

    app = _make_app()
    client = TestClient(app)

    resp = client.post(
        "/v1/workers/git-integrations",
        json={"kind": "github", "scope": "user", "token": "bad_token"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_returns_created_integration(monkeypatch):
    """GET lists integrations owned by the user/org."""
    import ai_portal.workers.git.connection_service as conn_svc

    fake_integration = _FakeIntegration()
    fake_repos = _make_repos()

    def _fake_list(db, *, owner_user_id, org_id):
        return [fake_integration]

    def _fake_list_repos(db, integration_id):
        return fake_repos

    monkeypatch.setattr(conn_svc, "list_integrations", _fake_list)
    monkeypatch.setattr(conn_svc, "list_repos", _fake_list_repos)

    app = _make_app()
    client = TestClient(app)

    resp = client.get("/v1/workers/git-integrations")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["account_login"] == "octocat"
    assert items[0]["id"] == str(_INTEGRATION_UUID)
    assert len(items[0]["repos"]) == 2


@pytest.mark.asyncio
async def test_patch_repos_flips_enabled(monkeypatch):
    """PATCH /{id}/repos enables the named repo and disables the rest."""
    import ai_portal.workers.git.connection_service as conn_svc

    fake_repos = _make_repos()

    def _fake_set_enabled(db, integration_id, enabled_full_names):
        for r in fake_repos:
            r.enabled = r.full_name in enabled_full_names
        return fake_repos

    monkeypatch.setattr(conn_svc, "set_enabled_repos", _fake_set_enabled)

    app = _make_app()
    client = TestClient(app)

    resp = client.patch(
        f"/v1/workers/git-integrations/{_INTEGRATION_UUID}/repos",
        json={"enabled_full_names": ["octocat/Hello-World"]},
    )
    assert resp.status_code == 200
    repos = resp.json()
    assert len(repos) == 2
    by_name = {r["full_name"]: r for r in repos}
    assert by_name["octocat/Hello-World"]["enabled"] is True
    assert by_name["octocat/Spoon-Knife"]["enabled"] is False


@pytest.mark.asyncio
async def test_delete_returns_204(monkeypatch):
    """DELETE /{id} → 204."""
    import ai_portal.workers.git.connection_service as conn_svc

    deleted = []

    def _fake_delete(db, integration_id):
        deleted.append(integration_id)

    monkeypatch.setattr(conn_svc, "delete_integration", _fake_delete)

    app = _make_app()
    client = TestClient(app)

    resp = client.delete(f"/v1/workers/git-integrations/{_INTEGRATION_UUID}")
    assert resp.status_code == 204
    assert _INTEGRATION_UUID in deleted


@pytest.mark.asyncio
async def test_get_repos_endpoint(monkeypatch):
    """GET /{id}/repos returns repo list."""
    import ai_portal.workers.git.connection_service as conn_svc

    fake_repos = _make_repos()

    def _fake_list_repos(db, integration_id):
        return fake_repos

    monkeypatch.setattr(conn_svc, "list_repos", _fake_list_repos)

    app = _make_app()
    client = TestClient(app)

    resp = client.get(f"/v1/workers/git-integrations/{_INTEGRATION_UUID}/repos")
    assert resp.status_code == 200
    repos = resp.json()
    assert len(repos) == 2
    names = {r["full_name"] for r in repos}
    assert "octocat/Hello-World" in names
    assert "octocat/Spoon-Knife" in names
