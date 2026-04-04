from fastapi.testclient import TestClient
from ai_portal.main import app

client = TestClient(app)


def test_setup_endpoint_returns_400_in_saas_mode(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-saas-mode")
    resp = client.post("/setup", json={
        "org_name": "Test Org",
        "admin_email": "admin@example.com",
        "admin_password": "AdminPass123!"
    })
    # 400 because deployment_mode is saas not selfhosted
    assert resp.status_code == 400


def test_setup_guard_middleware_importable():
    from ai_portal.middleware.setup_guard import SetupGuardMiddleware
    assert SetupGuardMiddleware is not None
