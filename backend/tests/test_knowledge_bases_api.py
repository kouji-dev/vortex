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
def test_put_conversation_knowledge_bases_unknown_kb_returns_404():
    cr = client.post("/api/chat/conversations", headers=AUTH, json={})
    cid = cr.json()["id"]
    r = client.put(
        f"/api/chat/conversations/{cid}/knowledge-bases",
        headers=AUTH,
        json={"knowledge_base_ids": [999_999]},
    )
    assert r.status_code == 404
