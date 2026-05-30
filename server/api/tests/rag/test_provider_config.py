"""Unit tests for the RAG deploy-vs-runtime provider config loader."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ai_portal.rag import provider_config as pc


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


# ── fallback (no YAML section) → full bundled set, enabled ────────────────


def test_no_yaml_falls_back_to_full_bundled_set(tmp_path):
    cfg = pc.load_provider_config(path=tmp_path / "missing.yaml", env={})
    vs = cfg.layer(pc.VECTOR_STORES)
    assert set(vs.available_ids()) == set(pc._BUNDLED_VECTOR_STORES)
    assert vs.enabled_ids() == vs.available_ids()  # all enabled by default
    assert vs.default_id == "pgvector"


def test_each_layer_has_a_default_except_connectors(tmp_path):
    cfg = pc.load_provider_config(path=tmp_path / "missing.yaml", env={})
    assert cfg.layer(pc.EMBEDDERS).default_id == "voyage-3"
    assert cfg.layer(pc.RERANKERS).default_id == "voyage-rerank-2"
    assert cfg.layer(pc.SEARCH_PROVIDERS).default_id == "tavily"
    assert cfg.layer(pc.CONNECTORS).default_id is None


# ── YAML narrows the universe ─────────────────────────────────────────────


def test_yaml_items_narrow_available_set(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
        rag_providers:
          vector_stores:
            default: qdrant
            items:
              - id: pgvector
              - id: qdrant
                endpoint: http://qdrant:6333
                credential_env: QDRANT_API_KEY
        """,
    )
    cfg = pc.load_provider_config(path=path, env={"QDRANT_API_KEY": "secret"})
    vs = cfg.layer(pc.VECTOR_STORES)
    # pinecone/weaviate are dropped — not declared
    assert set(vs.available_ids()) == {"pgvector", "qdrant"}
    assert vs.default_id == "qdrant"
    qdrant = vs.get("qdrant")
    assert qdrant is not None
    assert qdrant.endpoint == "http://qdrant:6333"
    assert qdrant.has_credential is True  # env set
    # credential value itself never leaks into the public view
    assert "secret" not in str(qdrant.to_public())


def test_unknown_yaml_id_is_dropped_not_invented(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
        rag_providers:
          embedders:
            items:
              - id: voyage-3
              - id: totally-made-up
        """,
    )
    cfg = pc.load_provider_config(path=path, env={})
    assert cfg.layer(pc.EMBEDDERS).available_ids() == ("voyage-3",)


def test_disabled_provider_not_selectable(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
        rag_providers:
          embedders:
            items:
              - id: voyage-3
              - id: text-embedding-3-small
                enabled: false
        """,
    )
    cfg = pc.load_provider_config(path=path, env={})
    emb = cfg.layer(pc.EMBEDDERS)
    assert emb.available_ids() == ("voyage-3", "text-embedding-3-small")
    assert emb.enabled_ids() == ("voyage-3",)
    assert emb.is_selectable("voyage-3") is True
    assert emb.is_selectable("text-embedding-3-small") is False


def test_credential_absent_marks_has_credential_false(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
        rag_providers:
          search_providers:
            items:
              - id: tavily
                credential_env: TAVILY_API_KEY
        """,
    )
    cfg = pc.load_provider_config(path=path, env={})  # no env
    assert cfg.layer(pc.SEARCH_PROVIDERS).get("tavily").has_credential is False


# ── default resolution precedence: env > yaml > fallback ──────────────────


def test_env_default_overrides_yaml(tmp_path, monkeypatch):
    path = _write_yaml(
        tmp_path,
        """
        rag_providers:
          vector_stores:
            default: pgvector
            items:
              - id: pgvector
              - id: qdrant
        """,
    )
    monkeypatch.setenv("RAG_VECTOR_STORE_DEFAULT", "qdrant")
    cfg = pc.load_provider_config(path=path)
    assert cfg.layer(pc.VECTOR_STORES).default_id == "qdrant"


def test_default_falls_back_when_not_in_declared_set(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
        rag_providers:
          vector_stores:
            default: pinecone
            items:
              - id: pgvector
              - id: qdrant
        """,
    )
    cfg = pc.load_provider_config(path=path, env={})
    # pinecone not declared → pick a declared id instead
    assert cfg.layer(pc.VECTOR_STORES).default_id in {"pgvector", "qdrant"}


# ── enforcement helpers ───────────────────────────────────────────────────


def test_ensure_selectable_passes_and_rejects(tmp_path):
    cfg = pc.load_provider_config(path=tmp_path / "missing.yaml", env={})
    assert pc.ensure_selectable(pc.VECTOR_STORES, "pgvector", cfg=cfg) == "pgvector"
    with pytest.raises(pc.ProviderNotSelectable):
        pc.ensure_selectable(pc.VECTOR_STORES, "bogus", cfg=cfg)


def test_ensure_selectable_rejects_disabled(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
        rag_providers:
          rerankers:
            items:
              - id: voyage-rerank-2
              - id: cohere-rerank-3.5
                enabled: false
        """,
    )
    cfg = pc.load_provider_config(path=path, env={})
    with pytest.raises(pc.ProviderNotSelectable):
        pc.ensure_selectable(pc.RERANKERS, "cohere-rerank-3.5", cfg=cfg)


def test_to_public_round_trips_every_layer(tmp_path):
    cfg = pc.load_provider_config(path=tmp_path / "missing.yaml", env={})
    pub = cfg.to_public()
    assert set(pub) == set(pc.LAYERS)
    for layer_name in pc.LAYERS:
        assert pub[layer_name]["layer"] == layer_name
        assert isinstance(pub[layer_name]["items"], list)


def test_cache_reset(tmp_path):
    a = pc.get_provider_config()
    assert pc.get_provider_config() is a  # cached
    pc.reset_cache()
    assert pc.get_provider_config() is not a
