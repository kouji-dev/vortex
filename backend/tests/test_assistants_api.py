from fastapi.testclient import TestClient

from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)

AUTH = {"Authorization": "Bearer devtoken"}


@requires_postgres
def test_assistant_patch_owner():
    ca = client.post(
        "/api/assistants",
        headers=AUTH,
        json={"name": "orig", "description": "d", "system_prompt": "p", "visibility": "private"},
    )
    assert ca.status_code == 201, ca.text
    aid = ca.json()["id"]

    r = client.patch(
        f"/api/assistants/{aid}",
        headers=AUTH,
        json={"name": "renamed", "system_prompt": "new prompt"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "renamed"
    assert body["system_prompt"] == "new prompt"
    assert body["description"] == "d"
