"""RAG retrieval unit tests."""
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import requires_postgres


@requires_postgres
def test_rag_module_importable():
    from ai_portal.services import rag as rag_mod

    assert rag_mod.retrieve_context_with_meta is not None
    assert rag_mod.search_knowledge_base_tool is not None


def test_returns_empty_when_no_kb_ids():
    from ai_portal.services.rag import retrieve_context_with_meta

    db = MagicMock()
    context, meta = retrieve_context_with_meta(db, knowledge_base_ids=[], query_embedding=[0.1] * 3)
    assert context == ""
    assert meta == []


def test_returns_meta_per_kb():
    """Meta list has one entry per KB that contributed chunks."""
    from ai_portal.models import Document, DocumentChunk
    from ai_portal.models.knowledge_base import KnowledgeBase
    from ai_portal.services.rag import retrieve_context_with_meta

    kb1 = MagicMock(spec=KnowledgeBase)
    kb1.id = 1
    kb1.name = "HR Policies"

    chunk1 = MagicMock(spec=DocumentChunk)
    chunk1.content = "Remote work policy text"
    chunk1.embedding = [0.1] * 3
    chunk1.meta = {"source": "Remote Work p.14"}
    chunk1.document_id = 10

    doc1 = MagicMock(spec=Document)
    doc1.id = 10
    doc1.knowledge_base_id = 1

    call_count = 0
    scalars_results = [
        [chunk1],  # chunks query — iterated via list()
        [doc1],    # doc objects — .all()
        [kb1],     # kbs — .all()
    ]

    def scalars_side_effect(*args, **kwargs):
        nonlocal call_count
        result = scalars_results[call_count]
        call_count += 1
        m = MagicMock()
        m.__iter__ = MagicMock(return_value=iter(result))
        m.all.return_value = result
        return m

    db = MagicMock()
    db.scalars.side_effect = scalars_side_effect

    with patch("ai_portal.services.rag._cosine_score", return_value=0.91):
        context, meta = retrieve_context_with_meta(
            db, knowledge_base_ids=[1], query_embedding=[0.1] * 3
        )

    assert "Remote work policy text" in context
    assert len(meta) == 1
    assert meta[0]["kb_id"] == 1
    assert meta[0]["kb_name"] == "HR Policies"
    assert meta[0]["chunks_used"] == 1
    assert meta[0]["top_score"] == 0.91
    assert meta[0]["sections"] == ["Remote Work p.14"]


def test_cosine_score_plain_list_embeddings():
    from ai_portal.models import DocumentChunk
    from ai_portal.services.rag import _cosine_score

    c = MagicMock(spec=DocumentChunk)
    c.embedding = [1.0, 0.0, 0.0]
    assert _cosine_score(c, [1.0, 0.0, 0.0]) == 1.0
    assert _cosine_score(c, [0.0, 1.0, 0.0]) == 0.0


def test_cosine_score_numpy_ndarray_embeddings():
    numpy = pytest.importorskip("numpy")
    from ai_portal.models import DocumentChunk
    from ai_portal.services.rag import _cosine_score

    c = MagicMock(spec=DocumentChunk)
    c.embedding = numpy.array([1.0, 0.0, 0.0], dtype=numpy.float64)
    assert abs(_cosine_score(c, [1.0, 0.0, 0.0]) - 1.0) < 1e-9
