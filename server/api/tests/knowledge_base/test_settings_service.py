"""Unit tests for KB provider-settings validation + apply (deploy-vs-runtime)."""
from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_portal.knowledge_base import settings_service as ss
from ai_portal.rag import provider_config as pc


def _cfg(tmp_path: Path, body: str) -> pc.ProviderConfig:
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return pc.load_provider_config(path=p, env={})


class _FakeDb:
    """Minimal Session double — apply_settings only commits/refreshes."""

    def __init__(self) -> None:
        self.committed = False

    def commit(self) -> None:
        self.committed = True

    def refresh(self, _obj) -> None:  # noqa: D401 - no-op
        pass


def _kb() -> SimpleNamespace:
    return SimpleNamespace(
        embedder_id="voyage-3",
        vector_backend="pgvector",
        chunker_id="fixed_token",
        default_retrieval_policy_id=None,
        language=None,
        settings_json={},
    )


# ── validation against the declared set ──────────────────────────────────


def test_valid_selection_passes(tmp_path):
    cfg = _cfg(
        tmp_path,
        """
        rag_providers:
          vector_stores:
            items:
              - id: pgvector
              - id: qdrant
        """,
    )
    patch = ss.validate_settings_patch(vector_backend="qdrant", cfg=cfg)
    assert patch.vector_backend == "qdrant"


def test_undeclared_vector_backend_rejected(tmp_path):
    cfg = _cfg(
        tmp_path,
        """
        rag_providers:
          vector_stores:
            items:
              - id: pgvector
        """,
    )
    with pytest.raises(ss.InvalidKbSetting):
        ss.validate_settings_patch(vector_backend="pinecone", cfg=cfg)


def test_disabled_embedder_rejected(tmp_path):
    cfg = _cfg(
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
    with pytest.raises(ss.InvalidKbSetting):
        ss.validate_settings_patch(embedder_id="text-embedding-3-small", cfg=cfg)


def test_reranker_validated_against_declared_set(tmp_path):
    cfg = _cfg(
        tmp_path,
        """
        rag_providers:
          rerankers:
            items:
              - id: voyage-rerank-2
        """,
    )
    assert ss.validate_settings_patch(reranker_id="voyage-rerank-2", cfg=cfg)
    with pytest.raises(ss.InvalidKbSetting):
        ss.validate_settings_patch(reranker_id="cohere-rerank-3.5", cfg=cfg)


def test_chunker_validated_against_bundled_registry(tmp_path):
    cfg = _cfg(tmp_path, "rag_providers: {}\n")
    # fixed_token is a bundled chunker; bogus is not.
    assert ss.validate_settings_patch(chunker_id="fixed_token", cfg=cfg)
    with pytest.raises(ss.InvalidKbSetting):
        ss.validate_settings_patch(chunker_id="bogus_chunker", cfg=cfg)


def test_language_length_bounded(tmp_path):
    cfg = _cfg(tmp_path, "rag_providers: {}\n")
    with pytest.raises(ss.InvalidKbSetting):
        ss.validate_settings_patch(language="too-long-language", cfg=cfg)


def test_none_fields_skipped(tmp_path):
    cfg = _cfg(tmp_path, "rag_providers: {}\n")
    patch = ss.validate_settings_patch(language="en", cfg=cfg)
    assert patch.embedder_id is None
    assert patch.vector_backend is None
    assert patch.language == "en"


# ── apply ─────────────────────────────────────────────────────────────────


def test_apply_settings_persists_columns_and_reranker_in_json():
    kb = _kb()
    db = _FakeDb()
    patch = ss.KbSettingsUpdate(
        embedder_id="voyage-3-lite",
        vector_backend="qdrant",
        reranker_id="bge-reranker-v2-m3",
        chunker_id="semantic",
        language="fr",
    )
    ss.apply_settings(db, kb, patch)
    assert kb.embedder_id == "voyage-3-lite"
    assert kb.vector_backend == "qdrant"
    assert kb.chunker_id == "semantic"
    assert kb.language == "fr"
    # reranker has no column — lives in settings_json
    assert kb.settings_json["reranker_id"] == "bge-reranker-v2-m3"
    assert db.committed is True


def test_apply_settings_only_sets_provided_fields():
    kb = _kb()
    db = _FakeDb()
    ss.apply_settings(db, kb, ss.KbSettingsUpdate(language="es"))
    assert kb.language == "es"
    assert kb.embedder_id == "voyage-3"  # untouched
    assert kb.vector_backend == "pgvector"  # untouched
    assert "reranker_id" not in kb.settings_json
