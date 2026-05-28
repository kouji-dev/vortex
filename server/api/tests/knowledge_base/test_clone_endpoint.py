"""KB clone endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)
AUTH = {"Authorization": "Bearer devtoken"}


@requires_postgres
def test_clone_kb_basic():
    src = client.post(
        "/api/knowledge-bases",
        headers=AUTH,
        json={"name": "src-kb", "description": "to clone"},
    )
    assert src.status_code == 201, src.text
    src_id = src.json()["id"]

    r = client.post(
        f"/api/knowledge-bases/{src_id}/clone",
        headers=AUTH,
        json={"name": "cloned-kb", "include_documents": False},
    )
    assert r.status_code == 201, r.text
    dst = r.json()
    assert dst["name"] == "cloned-kb"
    assert dst["id"] != src_id


@requires_postgres
def test_clone_kb_404_missing_src():
    r = client.post(
        "/api/knowledge-bases/9999999/clone",
        headers=AUTH,
        json={"name": "x"},
    )
    assert r.status_code == 404


@requires_postgres
def test_clone_kb_rejects_empty_name():
    src = client.post("/api/knowledge-bases", headers=AUTH, json={"name": "x"})
    assert src.status_code == 201
    r = client.post(
        f"/api/knowledge-bases/{src.json()['id']}/clone",
        headers=AUTH,
        json={"name": ""},
    )
    assert r.status_code in (400, 422)
