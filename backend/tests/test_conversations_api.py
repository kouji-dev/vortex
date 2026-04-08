from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_portal.core.db.session import SessionLocal
from ai_portal.main import app
from ai_portal.catalog.service import (
    resolve_default_conversation_stored_model,
)
from tests.conftest import requires_postgres

client = TestClient(app)

AUTH = {"Authorization": "Bearer devtoken"}


def test_starters_public_without_auth():
    r = client.get("/api/chat/starters")
    assert r.status_code == 200
    assert "sections" in r.json()


@requires_postgres
def test_starters_ok():
    r = client.get("/api/chat/starters", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert "sections" in body


@requires_postgres
def test_create_conversation_defaults_model_and_settings():
    db = SessionLocal()
    try:
        expected_model = resolve_default_conversation_stored_model(db)
    finally:
        db.close()
    r = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["settings"] == {
        "capabilities": {
            "reflection": False,
            "research": False,
            "web": False,
            "web_search": False,
            "data_query": False,
        },
    }
    assert body["model"] == expected_model


@requires_postgres
def test_create_conversation_with_knowledge_base_ids():
    kb = client.post(
        "/api/knowledge-bases",
        headers=AUTH,
        json={"name": "create-with-kb", "description": ""},
    )
    assert kb.status_code == 201, kb.text
    kb_id = kb.json()["id"]
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"knowledge_base_ids": [kb_id]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["knowledge_base_ids"] == [kb_id]
    cid = r.json()["id"]
    gr = client.get(f"/api/chat/conversations/{cid}", headers=AUTH)
    assert gr.status_code == 200, gr.text
    assert gr.json()["knowledge_base_ids"] == [kb_id]


@requires_postgres
def test_conversations_crud_and_messages():
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"settings": {"capabilities": {"web": True}}},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    cid = body["id"]
    assert body["settings"]["capabilities"]["web"] is True
    assert body["settings"]["capabilities"]["reflection"] is False
    assert body["settings"]["capabilities"]["research"] is False

    r = client.get("/api/chat/conversations", headers=AUTH)
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert cid in ids

    r = client.get(f"/api/chat/conversations/{cid}/messages", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []

    r = client.patch(
        f"/api/chat/conversations/{cid}",
        headers=AUTH,
        json={"title": "Renamed"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"

    r = client.patch(
        f"/api/chat/conversations/{cid}",
        headers=AUTH,
        json={"settings": None},
    )
    assert r.status_code == 200
    assert r.json()["settings"] is None


@requires_postgres
def test_conversations_settings_rejects_array():
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"settings": [1, 2, 3]},
    )
    assert r.status_code == 422


@requires_postgres
def test_conversations_settings_rejects_unknown_capability_key():
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"settings": {"capabilities": {"web": True, "nope": True}}},
    )
    assert r.status_code == 422


@requires_postgres
@patch("ai_portal.catalog.providers.langchain.LangChainChatProvider.stream_deltas_with_tools")
def test_first_stream_message_sets_title_from_prompt_truncated(mock_deltas, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mock_deltas.return_value = iter([{"type": "delta", "text": "x"}])

    r = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json().get("title") in (None, "")

    long_prompt = "a" * 200
    sr = client.post(
        f"/api/chat/conversations/{cid}/messages/stream",
        headers=AUTH,
        json={"content": long_prompt, "use_rag": False},
    )
    assert sr.status_code == 200, sr.text
    _ = sr.content

    gr = client.get(f"/api/chat/conversations/{cid}", headers=AUTH)
    assert gr.status_code == 200
    assert gr.json()["title"] == "a" * 125 + "..."

    mock_deltas.return_value = iter([{"type": "delta", "text": "y"}])
    sr2 = client.post(
        f"/api/chat/conversations/{cid}/messages/stream",
        headers=AUTH,
        json={"content": "second message", "use_rag": False},
    )
    assert sr2.status_code == 200, sr2.text
    _ = sr2.content

    gr2 = client.get(f"/api/chat/conversations/{cid}", headers=AUTH)
    assert gr2.json()["title"] == "a" * 125 + "..."


@requires_postgres
@patch("ai_portal.catalog.providers.langchain.LangChainChatProvider.stream_deltas_with_tools")
def test_stream_llm_error_persists_user_and_error_assistant(mock_deltas, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mock_deltas.side_effect = ValueError("model unavailable")

    r = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    sr = client.post(
        f"/api/chat/conversations/{cid}/messages/stream",
        headers=AUTH,
        json={"content": "user asks something", "use_rag": False},
    )
    assert sr.status_code == 200, sr.text
    raw = sr.content.decode()
    assert "model unavailable" in raw
    assert "done" in raw

    tail = client.get(
        f"/api/chat/conversations/{cid}/messages?limit=10&recent=true",
        headers=AUTH,
    )
    assert tail.status_code == 200, tail.text
    msgs = tail.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "user asks something"
    assert msgs[1]["role"] == "assistant"
    assert "**Error:**" in msgs[1]["content"]
    assert "model unavailable" in msgs[1]["content"]


@requires_postgres
@patch("ai_portal.catalog.providers.langchain.LangChainChatProvider.stream_deltas_with_tools")
def test_messages_recent_tail_and_before_id(mock_deltas, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mock_deltas.return_value = iter([{"type": "delta", "text": "ok"}])

    r = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    for i in range(2):
        sr = client.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": f"msg{i}", "use_rag": False},
        )
        assert sr.status_code == 200, sr.text
        _ = sr.content

    r = client.get(
        f"/api/chat/conversations/{cid}/messages?limit=2&recent=true",
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    tail = r.json()
    assert len(tail) == 2
    assert tail[0]["role"] == "user"
    assert tail[0]["content"] == "msg1"
    assert tail[1]["role"] == "assistant"
    before = tail[0]["id"]
    r2 = client.get(
        f"/api/chat/conversations/{cid}/messages?limit=10&recent=true&before_id={before}",
        headers=AUTH,
    )
    assert r2.status_code == 200, r2.text
    older = r2.json()
    assert len(older) == 2
    assert older[0]["role"] == "user"
    assert older[0]["content"] == "msg0"


@requires_postgres
def test_patch_assistant_id_requires_visible_assistant():
    r = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = client.patch(
        f"/api/chat/conversations/{cid}",
        headers=AUTH,
        json={"assistant_id": 999_999},
    )
    assert r.status_code == 404

    ca = client.post(
        "/api/assistants",
        headers=AUTH,
        json={"name": "link-me", "visibility": "org"},
    )
    assert ca.status_code == 201, ca.text
    aid = ca.json()["id"]
    r = client.patch(
        f"/api/chat/conversations/{cid}",
        headers=AUTH,
        json={"assistant_id": aid},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assistant_id"] == aid
    r = client.patch(
        f"/api/chat/conversations/{cid}",
        headers=AUTH,
        json={"assistant_id": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assistant_id"] is None


@requires_postgres
@patch("ai_portal.catalog.providers.langchain.LangChainChatProvider.stream_deltas_with_tools")
def test_patch_delete_and_regenerate_message(mock_deltas, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mock_deltas.return_value = iter([{"type": "delta", "text": "x"}])

    r = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    sr = client.post(
        f"/api/chat/conversations/{cid}/messages/stream",
        headers=AUTH,
        json={"content": "hello", "use_rag": False},
    )
    assert sr.status_code == 200, sr.text
    _ = sr.content

    msgs = client.get(
        f"/api/chat/conversations/{cid}/messages?recent=false&limit=20",
        headers=AUTH,
    ).json()
    assert len(msgs) == 2
    uid = next(m["id"] for m in msgs if m["role"] == "user")
    aid = next(m["id"] for m in msgs if m["role"] == "assistant")

    r = client.patch(
        f"/api/chat/conversations/{cid}/messages/{uid}",
        headers=AUTH,
        json={"content": "hello edited"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "hello edited"

    r = client.delete(
        f"/api/chat/conversations/{cid}/messages/{aid}",
        headers=AUTH,
    )
    assert r.status_code == 204, r.text

    msgs2 = client.get(
        f"/api/chat/conversations/{cid}/messages?recent=false",
        headers=AUTH,
    ).json()
    assert len(msgs2) == 1

    # new assistant reply, then regenerate
    mock_deltas.return_value = iter([{"type": "delta", "text": "y"}])
    sr2 = client.post(
        f"/api/chat/conversations/{cid}/messages/stream",
        headers=AUTH,
        json={"content": "again", "use_rag": False},
    )
    assert sr2.status_code == 200, sr2.text
    _ = sr2.content
    msgs3 = client.get(
        f"/api/chat/conversations/{cid}/messages?recent=false",
        headers=AUTH,
    ).json()
    aid2 = next(m["id"] for m in msgs3 if m["role"] == "assistant")
    mock_deltas.return_value = iter([{"type": "delta", "text": "z"}])
    sr3 = client.post(
        f"/api/chat/conversations/{cid}/messages/stream",
        headers=AUTH,
        json={"content": "", "regenerate_after_message_id": aid2, "use_rag": False},
    )
    assert sr3.status_code == 200, sr3.text
    _ = sr3.content
    msgs4 = client.get(
        f"/api/chat/conversations/{cid}/messages?recent=false",
        headers=AUTH,
    ).json()
    assert len(msgs4) == 3
    assert msgs4[-1]["role"] == "assistant"
    assert "z" in msgs4[-1]["content"]


