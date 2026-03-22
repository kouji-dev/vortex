from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_portal.config import get_settings
from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)

AUTH = {"Authorization": "Bearer devtoken"}


@requires_postgres
def test_chat_unknown_assistant():
    get_settings.cache_clear()
    r = client.post(
        "/api/chat",
        headers=AUTH,
        json={
            "assistant_id": 999_999,
            "messages": [{"role": "user", "content": "hi"}],
            "use_rag": False,
        },
    )
    assert r.status_code == 404


@requires_postgres
@patch("ai_portal.api.chat.llm_svc.chat_completions")
def test_chat_roundtrip(mock_llm, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    mock_llm.return_value = {"choices": [{"message": {"content": "ok"}}]}

    ca = client.post(
        "/api/assistants",
        headers=AUTH,
        json={"name": "pytest-bot", "visibility": "org"},
    )
    assert ca.status_code == 201, ca.text
    aid = ca.json()["id"]

    r = client.post(
        "/api/chat",
        headers=AUTH,
        json={
            "assistant_id": aid,
            "messages": [{"role": "user", "content": "hi"}],
            "use_rag": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "ok"
    assert "session_id" in body
