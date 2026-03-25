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
def test_put_conversation_knowledge_bases_unknown_kb_returns_404():
    cr = client.post("/api/chat/conversations", headers=AUTH, json={})
    cid = cr.json()["id"]
    r = client.put(
        f"/api/chat/conversations/{cid}/knowledge-bases",
        headers=AUTH,
        json={"knowledge_base_ids": [999_999]},
    )
    assert r.status_code == 404
