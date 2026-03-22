from fastapi.testclient import TestClient

from ai_portal.main import app

client = TestClient(app)


def test_list_assistants_unauthorized():
    r = client.get("/api/assistants")
    assert r.status_code == 401


def test_list_assistants_invalid_token():
    r = client.get("/api/assistants", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
