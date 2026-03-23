from fastapi.testclient import TestClient
from tests.conftest import requires_postgres

from ai_portal.main import app

client = TestClient(app)

AUTH = {"Authorization": "Bearer devtoken"}


@requires_postgres
def test_list_models_requires_auth():
    r = client.get("/api/models")
    assert r.status_code == 401


@requires_postgres
def test_list_models_returns_seed_rows(monkeypatch):
    monkeypatch.setenv("PORTAL_API_KEY_PEPPER", "test-pepper")
    from ai_portal.config import get_settings

    get_settings.cache_clear()
    r = client.get("/api/models", headers=AUTH)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) >= 2
    assert all("is_default" in row for row in data)
    assert sum(1 for row in data if row["is_default"]) == 1
    slugs = {row["slug"] for row in data}
    assert "openai-o3-mini" in slugs
    assert "example-locked-premium" not in slugs
    locked = next(x for x in data if x["slug"] == "openai-gpt-5-3-codex")
    assert locked["accessible"] is False
    assert locked["can_request_access"] is True
    assert locked["request_access_url"] == "https://example.com/request-model-access"
    assert locked["model_settings"]["reasoning"]["supported"] is True
    assert locked["model_settings"]["reasoning"]["efforts_available"] == [
        "low",
        "medium",
        "high",
    ]
    assert locked["model_settings"]["reasoning"]["default_effort"] == "high"
    assert locked["model_settings"]["sampling"]["temperature"] is not None
    assert locked["model_settings"]["sampling"]["max_output_tokens"]["max"] == 128_000
    assert locked["model_settings"]["limits"]["max_input_chars"] == 1_048_576
    open_row = next(x for x in data if x["slug"] == "openai-o3-mini")
    assert open_row["accessible"] is True
    assert open_row["can_request_access"] is False
    assert open_row["model_settings"]["reasoning"]["supported"] is True
    assert open_row["model_settings"]["features"]["vision"] is True
    assert open_row["model_settings"]["sampling"]["max_output_tokens"]["max"] == 100_000
    assert open_row["model_settings"]["limits"]["max_input_chars"] == 1_048_576
