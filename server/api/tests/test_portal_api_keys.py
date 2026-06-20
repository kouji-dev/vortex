import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai_portal.auth.model import Org, User
from ai_portal.auth.strategies.jwt import create_access_token
from ai_portal.core.config import get_settings
from ai_portal.main import app
from tests.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.fixture()
def seeded_user(db_session: Session):
    """Create an Org + active User, flush so IDs are available."""
    org = Org(slug=f"test-{_uuid.uuid4().hex[:8]}", name="Test Org")
    db_session.add(org)
    db_session.flush()

    user = User(
        uuid=_uuid.uuid4(),
        email=f"test-{_uuid.uuid4().hex[:8]}@example.com",
        org_id=org.id,
        role="owner",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    return user, org


@requires_postgres
def test_portal_api_key_auth_roundtrip(monkeypatch, seeded_user):
    monkeypatch.setenv("PORTAL_API_KEY_PEPPER", "test-pepper")
    user, org = seeded_user

    settings = get_settings()
    token = create_access_token(
        user_uuid=user.uuid,
        org_id=org.id,
        role=user.role,
        secret=settings.secret_key,
    )
    auth_headers = {"Authorization": f"Bearer {token}"}

    client = TestClient(app)

    cr = client.post(
        "/api/me/portal-api-keys",
        headers=auth_headers,
        json={"label": "codex"},
    )
    assert cr.status_code == 201, cr.text
    api_token = cr.json()["token"]
    assert api_token.startswith("aip_")

    me = client.get("/api/me", headers={"Authorization": f"Bearer {api_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == user.email

    kid = cr.json()["id"]
    dr = client.delete(f"/api/me/portal-api-keys/{kid}", headers=auth_headers)
    assert dr.status_code == 204

    me2 = client.get("/api/me", headers={"Authorization": f"Bearer {api_token}"})
    assert me2.status_code == 401
