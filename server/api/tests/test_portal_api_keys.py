from fastapi.testclient import TestClient

from ai_portal.core.config import get_settings
from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)

DEV = {"Authorization": "Bearer devtoken"}


@requires_postgres
def test_portal_api_key_auth_roundtrip(monkeypatch):
    monkeypatch.setenv("PORTAL_API_KEY_PEPPER", "test-pepper")
    cr = client.post(
        "/api/me/portal-api-keys",
        headers=DEV,
        json={"label": "codex"},
    )
    assert cr.status_code == 201, cr.text
    token = cr.json()["token"]
    assert token.startswith("aip_")

    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == get_settings().dev_seed_user_email

    kid = cr.json()["id"]
    dr = client.delete(f"/api/me/portal-api-keys/{kid}", headers=DEV)
    assert dr.status_code == 204

    me2 = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me2.status_code == 401
