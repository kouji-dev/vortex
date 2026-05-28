"""Phase A+: per-KB scoped API key HTTP surface.

POST /api/knowledge-bases/{id}/api-keys     → mint, returns plaintext once
GET  /api/knowledge-bases/{id}/api-keys     → list (no plaintext)
DELETE /api/knowledge-bases/{id}/api-keys/{key_id} → revoke
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)
AUTH = {"Authorization": "Bearer devtoken"}


@requires_postgres
def test_mint_list_revoke_scoped_kb_key():
    kb = client.post(
        "/api/knowledge-bases",
        headers=AUTH,
        json={"name": "scoped-key-kb", "description": ""},
    )
    assert kb.status_code == 201, kb.text
    kb_id = kb.json()["id"]

    # GET empty
    r = client.get(f"/api/knowledge-bases/{kb_id}/api-keys", headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json() == []

    # Mint
    mint = client.post(
        f"/api/knowledge-bases/{kb_id}/api-keys",
        headers=AUTH,
        json={"name": "readonly-key"},
    )
    assert mint.status_code == 201, mint.text
    payload = mint.json()
    assert payload["name"] == "readonly-key"
    assert payload["plaintext"].startswith("ap_")
    key_id = payload["id"]
    # KB binding present
    assert f"kb:{kb_id}" in payload["scopes"]
    assert "kb:read" in payload["scopes"]
    assert "kb:answer" in payload["scopes"]

    # List shows it, no plaintext
    r = client.get(f"/api/knowledge-bases/{kb_id}/api-keys", headers=AUTH)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == key_id
    assert "plaintext" not in items[0]
    assert items[0]["prefix"].startswith("ap_")

    # Revoke
    rev = client.delete(
        f"/api/knowledge-bases/{kb_id}/api-keys/{key_id}",
        headers=AUTH,
    )
    assert rev.status_code == 204, rev.text

    # After revoke, list excludes it
    r = client.get(f"/api/knowledge-bases/{kb_id}/api-keys", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


@requires_postgres
def test_other_kb_keys_not_listed():
    """Listing /api/knowledge-bases/{id}/api-keys must scope to that KB only."""
    a = client.post("/api/knowledge-bases", headers=AUTH, json={"name": "kb-a"})
    b = client.post("/api/knowledge-bases", headers=AUTH, json={"name": "kb-b"})
    assert a.status_code == 201 and b.status_code == 201
    a_id, b_id = a.json()["id"], b.json()["id"]

    client.post(f"/api/knowledge-bases/{a_id}/api-keys", headers=AUTH, json={"name": "a-key"})
    client.post(f"/api/knowledge-bases/{b_id}/api-keys", headers=AUTH, json={"name": "b-key"})

    rb = client.get(f"/api/knowledge-bases/{b_id}/api-keys", headers=AUTH).json()
    assert len(rb) == 1
    assert rb[0]["name"] == "b-key"

    ra = client.get(f"/api/knowledge-bases/{a_id}/api-keys", headers=AUTH).json()
    assert len(ra) == 1
    assert ra[0]["name"] == "a-key"


@requires_postgres
def test_revoke_wrong_kb_404():
    kb = client.post("/api/knowledge-bases", headers=AUTH, json={"name": "kb-x"})
    kb2 = client.post("/api/knowledge-bases", headers=AUTH, json={"name": "kb-y"})
    assert kb.status_code == 201 and kb2.status_code == 201
    kb_id = kb.json()["id"]
    kb2_id = kb2.json()["id"]

    minted = client.post(
        f"/api/knowledge-bases/{kb_id}/api-keys",
        headers=AUTH,
        json={"name": "k"},
    ).json()
    key_id = minted["id"]

    # Try to revoke via the WRONG kb → 404
    r = client.delete(
        f"/api/knowledge-bases/{kb2_id}/api-keys/{key_id}",
        headers=AUTH,
    )
    assert r.status_code == 404


@requires_postgres
def test_mint_on_missing_kb_404():
    r = client.post(
        "/api/knowledge-bases/9999999/api-keys",
        headers=AUTH,
        json={"name": "x"},
    )
    assert r.status_code == 404
