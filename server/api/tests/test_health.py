from fastapi.testclient import TestClient

from ai_portal.main import app


def test_health_ok() -> None:
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["auth_mode"] == "dev"
    assert data["api"]["post_knowledge_bases"] is True
