"""Phase A: KnowledgeBase model carries RAG management fields."""

from __future__ import annotations

from ai_portal.knowledge_base.model import (
    KbAcl,
    KbChunk,
    KbDocStatus,
    KbDocument,
    KbDocumentVersion,
    KbStatus,
    KbVisibility,
    KnowledgeBase,
)


def test_kb_visibility_enum_values():
    assert KbVisibility.private.value == "private"
    assert KbVisibility.team.value == "team"
    assert KbVisibility.org_public.value == "org_public"


def test_kb_status_enum_values():
    assert KbStatus.active.value == "active"
    assert KbStatus.archived.value == "archived"
    assert KbStatus.deleted.value == "deleted"


def test_kb_doc_status_enum_values():
    assert KbDocStatus.pending.value == "pending"
    assert KbDocStatus.indexed.value == "indexed"
    assert KbDocStatus.quarantined.value == "quarantined"
    assert KbDocStatus.superseded.value == "superseded"
    assert KbDocStatus.deleted.value == "deleted"


def test_kb_table_has_management_columns():
    cols = {c.name for c in KnowledgeBase.__table__.columns}
    assert {
        "visibility",
        "embedder_id",
        "vector_backend",
        "chunker_id",
        "settings_json",
        "status",
        "slug",
        "tags",
        "default_retrieval_policy_id",
        "language",
    }.issubset(cols)


def test_kb_unique_org_slug_constraint_present():
    constraints = {c.name for c in KnowledgeBase.__table__.constraints}
    assert "uq_knowledge_bases_org_slug" in constraints


def test_kb_document_schema():
    cols = {c.name for c in KbDocument.__table__.columns}
    assert {
        "id",
        "kb_id",
        "source_uri",
        "title",
        "mime",
        "content_hash",
        "language",
        "source_acl_json",
        "meta_json",
        "status",
        "latest_version_id",
        "quarantine_reason",
        "connector_id",
        "created_at",
        "updated_at",
    } <= cols
    constraints = {c.name for c in KbDocument.__table__.constraints}
    assert "uq_kb_doc_uri" in constraints


def test_kb_document_version_schema():
    cols = {c.name for c in KbDocumentVersion.__table__.columns}
    assert {
        "id",
        "document_id",
        "version_no",
        "content_hash",
        "blob_ref",
        "meta_json",
        "created_at",
    } <= cols
    constraints = {c.name for c in KbDocumentVersion.__table__.constraints}
    assert "uq_kb_doc_version" in constraints


def test_kb_chunk_schema():
    cols = {c.name for c in KbChunk.__table__.columns}
    assert {
        "id",
        "document_id",
        "kb_id",
        "chunk_index",
        "token_count",
        "text",
        "embedding_ref",
        "acl_json",
        "meta_json",
    } <= cols


def test_kb_acl_schema():
    cols = {c.name for c in KbAcl.__table__.columns}
    assert {
        "id",
        "kb_id",
        "document_id",
        "chunk_id",
        "subject_kind",
        "subject_id",
    } <= cols


def test_kb_default_values_pythonside():
    kb = KnowledgeBase()
    # SQLAlchemy applies defaults on insert; we assert the descriptor knows them.
    assert KnowledgeBase.__table__.c.visibility.default.arg == "private"
    assert KnowledgeBase.__table__.c.status.default.arg == "active"
    assert KnowledgeBase.__table__.c.chunker_id.default.arg == "fixed_token"
    assert KnowledgeBase.__table__.c.vector_backend.default.arg == "pgvector"
    assert kb is not None
