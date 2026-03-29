from fastapi.testclient import TestClient

from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)

AUTH = {"Authorization": "Bearer devtoken"}


@requires_postgres
def test_knowledge_base_crud_and_conversation_attach():
    r = client.post(
        "/api/knowledge-bases",
        headers=AUTH,
        json={"name": "HR policies", "description": "internal"},
    )
    assert r.status_code == 201, r.text
    kb_id = r.json()["id"]

    r = client.get("/api/knowledge-bases", headers=AUTH)
    assert r.status_code == 200
    assert any(row["id"] == kb_id for row in r.json())

    cr = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert cr.status_code == 201, cr.text
    cid = cr.json()["id"]
    assert cr.json().get("knowledge_base_ids") == []

    r = client.put(
        f"/api/chat/conversations/{cid}/knowledge-bases",
        headers=AUTH,
        json={"knowledge_base_ids": [kb_id]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["knowledge_base_ids"] == [kb_id]

    r = client.get(f"/api/chat/conversations/{cid}", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["knowledge_base_ids"] == [kb_id]


@requires_postgres
def test_list_patch_delete_documents():
    kb = client.post(
        "/api/knowledge-bases",
        headers=AUTH,
        json={"name": "doc-list-kb", "description": ""},
    )
    assert kb.status_code == 201, kb.text
    kb_id = kb.json()["id"]

    r = client.get(f"/api/knowledge-bases/{kb_id}/documents", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []

    patch = client.patch(
        f"/api/knowledge-bases/{kb_id}",
        headers=AUTH,
        json={"name": "renamed-kb", "description": "d"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["name"] == "renamed-kb"

    # No file upload in unit test — skip delete of missing doc
    del404 = client.delete(
        f"/api/knowledge-bases/{kb_id}/documents/999999",
        headers=AUTH,
    )
    assert del404.status_code == 404


@requires_postgres
def test_connectors_crud_and_sync_job_runs():
    kb = client.post(
        "/api/knowledge-bases",
        headers=AUTH,
        json={"name": "connector-kb", "description": ""},
    )
    assert kb.status_code == 201, kb.text
    kb_id = kb.json()["id"]

    empty = client.get(f"/api/knowledge-bases/{kb_id}/connectors", headers=AUTH)
    assert empty.status_code == 200
    assert empty.json() == []

    cr = client.post(
        f"/api/knowledge-bases/{kb_id}/connectors",
        headers=AUTH,
        json={
            "kind": "gitlab",
            "label": "Handbook",
            "settings": {"project_id": "123"},
        },
    )
    assert cr.status_code == 201, cr.text
    cid = cr.json()["id"]
    assert cr.json()["kind"] == "gitlab"

    sync = client.post(
        f"/api/knowledge-bases/{kb_id}/connectors/{cid}/sync",
        headers=AUTH,
    )
    assert sync.status_code == 201, sync.text
    job_id = sync.json()["id"]

    jobs = client.get(f"/api/knowledge-bases/{kb_id}/connector-jobs", headers=AUTH)
    assert jobs.status_code == 200
    rows = jobs.json()
    assert rows and rows[0]["id"] == job_id
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["meta"].get("implementation") == "pending"

    del_c = client.delete(
        f"/api/knowledge-bases/{kb_id}/connectors/{cid}",
        headers=AUTH,
    )
    assert del_c.status_code == 204


@requires_postgres
def test_put_conversation_knowledge_bases_unknown_kb_returns_404():
    cr = client.post("/api/chat/conversations", headers=AUTH, json={})
    cid = cr.json()["id"]
    r = client.put(
        f"/api/chat/conversations/{cid}/knowledge-bases",
        headers=AUTH,
        json={"knowledge_base_ids": [999_999]},
    )
    assert r.status_code == 404


@requires_postgres
def test_stream_stores_used_kbs_in_extra():
    """When RAG runs and returns chunks, assistant message.extra contains used_kbs."""
    from unittest.mock import patch

    # Create a KB and a conversation, then attach the KB
    kb_res = client.post(
        "/api/knowledge-bases",
        headers=AUTH,
        json={"name": "Test KB", "description": ""},
    )
    assert kb_res.status_code == 201, kb_res.text
    kb_id = kb_res.json()["id"]

    conv_res = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"title": "test", "model": None, "assistant_id": None, "settings": None},
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    attach_res = client.put(
        f"/api/chat/conversations/{conv_id}/knowledge-bases",
        headers=AUTH,
        json={"knowledge_base_ids": [kb_id]},
    )
    assert attach_res.status_code == 200

    fake_meta = [
        {
            "kb_id": kb_id,
            "kb_name": "Test KB",
            "chunks_used": 1,
            "top_score": 0.9,
            "sections": [],
        }
    ]

    with (
        patch(
            "ai_portal.api.conversations.embedding_svc.embed_texts",
            return_value=[[0.1, 0.2]],
        ),
        patch(
            "ai_portal.api.conversations.rag_svc.retrieve_context_with_meta",
            return_value=("some context", fake_meta),
        ),
        patch(
            "ai_portal.api.conversations.llm_svc.chat_completions_stream_deltas",
            return_value=iter(["Hello"]),
        ),
    ):
        stream_res = client.post(
            f"/api/chat/conversations/{conv_id}/messages/stream",
            json={"content": "hello", "use_rag": True},
            headers=AUTH,
        )
        assert stream_res.status_code == 200

    # Check that the assistant message has used_kbs in extra via messages API
    msgs_res = client.get(
        f"/api/chat/conversations/{conv_id}/messages",
        headers=AUTH,
    )
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0]["extra"] is not None
    assert "used_kbs" in assistant_msgs[0]["extra"]
    assert assistant_msgs[0]["extra"]["used_kbs"][0]["kb_name"] == "Test KB"
