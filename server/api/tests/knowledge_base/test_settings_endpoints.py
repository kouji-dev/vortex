"""Endpoint tests for KB providers-config + settings (deploy-vs-runtime)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)
AUTH = {"Authorization": "Bearer devtoken"}


def test_providers_config_lists_declared_set_no_db():
    """providers-config needs no DB — pure config + chunker registry read."""
    r = client.get("/api/knowledge-bases/providers-config", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    for layer in (
        "embedders",
        "vector_stores",
        "rerankers",
        "search_providers",
        "connectors",
    ):
        assert layer in body
        assert "items" in body[layer]
        assert isinstance(body[layer]["items"], list)
    # vector_stores always ships pgvector as a selectable default
    vs_ids = {i["id"] for i in body["vector_stores"]["items"]}
    assert "pgvector" in vs_ids
    # chunkers from the bundled registry
    assert "fixed_token" in body["chunkers"]


def test_providers_config_literal_path_wins_over_id_route():
    """`/providers-config` must not be captured by `/{knowledge_base_id}`."""
    r = client.get("/api/knowledge-bases/providers-config", headers=AUTH)
    assert r.status_code == 200  # not a 404/422 from int coercion


@requires_postgres
def test_patch_settings_accepts_declared_rejects_undeclared():
    created = client.post(
        "/api/knowledge-bases", headers=AUTH, json={"name": "settings-kb"}
    )
    assert created.status_code == 201, created.text
    kb_id = created.json()["id"]

    # valid: pgvector is always declared
    ok = client.patch(
        f"/api/knowledge-bases/{kb_id}/settings",
        headers=AUTH,
        json={"vector_backend": "pgvector"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["vector_backend"] == "pgvector"

    # invalid: a bogus backend is rejected (selection-from-set enforced)
    bad = client.patch(
        f"/api/knowledge-bases/{kb_id}/settings",
        headers=AUTH,
        json={"vector_backend": "definitely-not-a-backend"},
    )
    assert bad.status_code == 422, bad.text


@requires_postgres
def test_get_settings_round_trips_reranker_in_json():
    created = client.post(
        "/api/knowledge-bases", headers=AUTH, json={"name": "settings-kb-2"}
    )
    kb_id = created.json()["id"]
    client.patch(
        f"/api/knowledge-bases/{kb_id}/settings",
        headers=AUTH,
        json={"reranker_id": "voyage-rerank-2"},
    )
    got = client.get(f"/api/knowledge-bases/{kb_id}/settings", headers=AUTH)
    assert got.status_code == 200, got.text
    assert got.json()["reranker_id"] == "voyage-rerank-2"
