"""Tests for the GitHub connection service.

No real network. ``_github_get`` is monkeypatched to return canned responses
so every code-path executes without hitting api.github.com.

DB fixtures mirror the chat/conftest.py pattern: function-scoped session that
rolls back after each test.  Skipped when DATABASE_URL is not set / Postgres
is unreachable.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import ai_portal.auth.model  # noqa: F401 — loads orgs/users into shared metadata so GitIntegration FKs resolve
import ai_portal.workers.git.connection_service as svc
from ai_portal.workers.git.connection_service import (
    InvalidGitToken,
    connect_github,
    decrypt_token,
    delete_integration,
    list_integrations,
    list_repos,
    set_enabled_repos,
)

# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------

_ORG_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee01")
_USER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee02")


@pytest.fixture(scope="module")
def db_engine(sync_engine):
    """Re-export the root conftest sync_engine for this module."""
    return sync_engine


@pytest.fixture()
def db_session(db_engine):
    """Function-scoped session that rolls back after each test."""
    with db_engine.begin() as conn:
        session = Session(bind=conn)
        try:
            yield session
        finally:
            session.close()
            conn.rollback()


@pytest.fixture()
def org_and_user(db_session):
    """Insert a minimal org + user row; yield (org_id, user_uuid)."""
    existing_org = db_session.execute(
        text("SELECT id FROM orgs WHERE id = :id"), {"id": str(_ORG_ID)}
    ).first()
    if not existing_org:
        db_session.execute(
            text("INSERT INTO orgs (id, slug, name) VALUES (:id, 'git-svc-test', 'Git Svc Test')"),
            {"id": str(_ORG_ID)},
        )

    existing_user = db_session.execute(
        text("SELECT uuid FROM users WHERE uuid = :uid"), {"uid": str(_USER_ID)}
    ).first()
    if not existing_user:
        db_session.execute(
            text(
                "INSERT INTO users (id, email, uuid, org_id) "
                "VALUES (:id, 'gittest@example.com', :uid, :oid)"
            ),
            {"id": 99991, "uid": str(_USER_ID), "oid": str(_ORG_ID)},
        )
    db_session.flush()
    return _ORG_ID, _USER_ID


# ---------------------------------------------------------------------------
# HTTP stub helpers
# ---------------------------------------------------------------------------

_USER_RESPONSE = {"login": "octocat", "id": 1}
_REPOS_RESPONSE = [
    {"full_name": "octocat/web", "default_branch": "main"},
    {"full_name": "octocat/api", "default_branch": "develop"},
]


def _make_stub(user_status: int = 200, repos_status: int = 200):
    """Return an async function that replaces _github_get."""
    async def _stub(token: str, path: str) -> httpx.Response:
        if path == "/user":
            return httpx.Response(user_status, json=_USER_RESPONSE)
        if path.startswith("/user/repos"):
            return httpx.Response(repos_status, json=_REPOS_RESPONSE)
        return httpx.Response(404, json={})

    return _stub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_github_stores_login_and_repos(
    db_session, org_and_user, monkeypatch
):
    monkeypatch.setattr(svc, "_github_get", _make_stub())
    org_id, user_id = org_and_user

    integration = await connect_github(
        db_session,
        owner_user_id=user_id,
        org_id=None,
        token="ghp_test_token",
    )

    assert integration.account_login == "octocat"
    assert integration.kind == "github"
    assert integration.auth_type == "token"
    assert integration.user_id == user_id
    assert integration.org_id is None


@pytest.mark.asyncio
async def test_decrypt_token_roundtrip(db_session, org_and_user, monkeypatch):
    monkeypatch.setattr(svc, "_github_get", _make_stub())
    _, user_id = org_and_user
    # Use a different user UUID so no stale row from previous test (session rollback
    # handles isolation, but be explicit to avoid sequence issues).
    fresh_user = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee03")
    # Insert user
    existing = db_session.execute(
        text("SELECT uuid FROM users WHERE uuid = :uid"), {"uid": str(fresh_user)}
    ).first()
    if not existing:
        db_session.execute(
            text(
                "INSERT INTO users (id, email, uuid, org_id) "
                "VALUES (:id, 'gittest2@example.com', :uid, :oid)"
            ),
            {"id": 99992, "uid": str(fresh_user), "oid": str(_ORG_ID)},
        )
        db_session.flush()

    integration = await connect_github(
        db_session,
        owner_user_id=fresh_user,
        org_id=None,
        token="ghp_secret_abc",
    )

    assert decrypt_token(integration) == "ghp_secret_abc"


@pytest.mark.asyncio
async def test_connect_github_creates_two_repo_rows(
    db_session, org_and_user, monkeypatch
):
    monkeypatch.setattr(svc, "_github_get", _make_stub())
    _, user_id = org_and_user

    # fresh user so integration id is new
    fresh_user = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee04")
    existing = db_session.execute(
        text("SELECT uuid FROM users WHERE uuid = :uid"), {"uid": str(fresh_user)}
    ).first()
    if not existing:
        db_session.execute(
            text(
                "INSERT INTO users (id, email, uuid, org_id) "
                "VALUES (:id, 'gittest3@example.com', :uid, :oid)"
            ),
            {"id": 99993, "uid": str(fresh_user), "oid": str(_ORG_ID)},
        )
        db_session.flush()

    integration = await connect_github(
        db_session,
        owner_user_id=fresh_user,
        org_id=None,
        token="ghp_test_token",
    )

    repos = list_repos(db_session, integration.id)
    assert len(repos) == 2
    full_names = {r.full_name for r in repos}
    assert full_names == {"octocat/web", "octocat/api"}
    # All repos start disabled
    assert all(not r.enabled for r in repos)


@pytest.mark.asyncio
async def test_set_enabled_repos_flips_only_named(
    db_session, org_and_user, monkeypatch
):
    monkeypatch.setattr(svc, "_github_get", _make_stub())
    fresh_user = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee05")
    existing = db_session.execute(
        text("SELECT uuid FROM users WHERE uuid = :uid"), {"uid": str(fresh_user)}
    ).first()
    if not existing:
        db_session.execute(
            text(
                "INSERT INTO users (id, email, uuid, org_id) "
                "VALUES (:id, 'gittest4@example.com', :uid, :oid)"
            ),
            {"id": 99994, "uid": str(fresh_user), "oid": str(_ORG_ID)},
        )
        db_session.flush()

    integration = await connect_github(
        db_session,
        owner_user_id=fresh_user,
        org_id=None,
        token="ghp_test_token",
    )

    updated = set_enabled_repos(db_session, integration.id, {"octocat/web"})
    enabled = {r.full_name for r in updated if r.enabled}
    disabled = {r.full_name for r in updated if not r.enabled}
    assert enabled == {"octocat/web"}
    assert disabled == {"octocat/api"}


@pytest.mark.asyncio
async def test_connect_github_raises_on_bad_token(
    db_session, org_and_user, monkeypatch
):
    monkeypatch.setattr(svc, "_github_get", _make_stub(user_status=401))
    _, user_id = org_and_user

    with pytest.raises(InvalidGitToken):
        await connect_github(
            db_session,
            owner_user_id=user_id,
            org_id=None,
            token="ghp_bad",
        )


@pytest.mark.asyncio
async def test_connect_github_raises_when_both_owner_set(
    db_session, org_and_user, monkeypatch
):
    monkeypatch.setattr(svc, "_github_get", _make_stub())
    org_id, user_id = org_and_user

    with pytest.raises(ValueError, match="Exactly one"):
        await connect_github(
            db_session,
            owner_user_id=user_id,
            org_id=org_id,
            token="ghp_x",
        )


@pytest.mark.asyncio
async def test_connect_github_raises_when_no_owner_set(
    db_session, org_and_user, monkeypatch
):
    monkeypatch.setattr(svc, "_github_get", _make_stub())

    with pytest.raises(ValueError, match="Exactly one"):
        await connect_github(
            db_session,
            owner_user_id=None,
            org_id=None,
            token="ghp_x",
        )


@pytest.mark.asyncio
async def test_list_integrations_by_user(db_session, org_and_user, monkeypatch):
    monkeypatch.setattr(svc, "_github_get", _make_stub())
    fresh_user = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee06")
    existing = db_session.execute(
        text("SELECT uuid FROM users WHERE uuid = :uid"), {"uid": str(fresh_user)}
    ).first()
    if not existing:
        db_session.execute(
            text(
                "INSERT INTO users (id, email, uuid, org_id) "
                "VALUES (:id, 'gittest5@example.com', :uid, :oid)"
            ),
            {"id": 99995, "uid": str(fresh_user), "oid": str(_ORG_ID)},
        )
        db_session.flush()

    await connect_github(
        db_session,
        owner_user_id=fresh_user,
        org_id=None,
        token="ghp_test_token",
    )

    found = list_integrations(db_session, owner_user_id=fresh_user, org_id=None)
    assert any(i.user_id == fresh_user for i in found)


@pytest.mark.asyncio
async def test_delete_integration_removes_row(db_session, org_and_user, monkeypatch):
    monkeypatch.setattr(svc, "_github_get", _make_stub())
    fresh_user = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee07")
    existing = db_session.execute(
        text("SELECT uuid FROM users WHERE uuid = :uid"), {"uid": str(fresh_user)}
    ).first()
    if not existing:
        db_session.execute(
            text(
                "INSERT INTO users (id, email, uuid, org_id) "
                "VALUES (:id, 'gittest6@example.com', :uid, :oid)"
            ),
            {"id": 99996, "uid": str(fresh_user), "oid": str(_ORG_ID)},
        )
        db_session.flush()

    integration = await connect_github(
        db_session,
        owner_user_id=fresh_user,
        org_id=None,
        token="ghp_test_token",
    )
    int_id = integration.id

    delete_integration(db_session, int_id)

    from sqlalchemy import select as sa_select
    from ai_portal.workers.model import GitIntegration as GI
    remaining = db_session.scalars(sa_select(GI).where(GI.id == int_id)).first()
    assert remaining is None
