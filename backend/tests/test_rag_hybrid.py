"""Tests for hybrid BM25+vector search, RRF merge, and search_knowledge_base_tool."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_portal.rag.service import _rrf_merge

# ---------------------------------------------------------------------------
# _rrf_merge
# ---------------------------------------------------------------------------

def test_rrf_merge_combines_rankings():
    vector_ids = [1, 2, 3]
    bm25_ids = [3, 1, 4]
    merged = _rrf_merge(vector_ids, bm25_ids, k=60)
    # IDs appearing in both lists should rank higher than single-list IDs
    assert merged[0] in {1, 3}
    assert set(merged) == {1, 2, 3, 4}


def test_rrf_merge_handles_empty_bm25():
    assert _rrf_merge([1, 2, 3], [], k=60) == [1, 2, 3]


def test_rrf_merge_handles_empty_vector():
    assert _rrf_merge([], [1, 2], k=60) == [1, 2]


def test_rrf_merge_both_empty():
    assert _rrf_merge([], [], k=60) == []


def test_rrf_merge_identical_lists():
    merged = _rrf_merge([5, 6, 7], [5, 6, 7], k=60)
    assert merged == [5, 6, 7]


def test_rrf_merge_disjoint_lists():
    merged = _rrf_merge([1, 2], [3, 4], k=60)
    assert set(merged) == {1, 2, 3, 4}
    assert merged[0] in {1, 3}  # rank-1 from either list


def test_rrf_merge_respects_k_parameter():
    """With a very small k, rank differences are amplified."""
    merged_small_k = _rrf_merge([1, 2, 3], [3, 2, 1], k=1)
    merged_large_k = _rrf_merge([1, 2, 3], [3, 2, 1], k=1000)
    # Both should produce same set; ordering may differ
    assert set(merged_small_k) == {1, 2, 3}
    assert set(merged_large_k) == {1, 2, 3}


# ---------------------------------------------------------------------------
# _rerank_chunks — cosine fallback
# ---------------------------------------------------------------------------

def test_rerank_chunks_cosine_fallback():
    from ai_portal.rag.service import _rerank_chunks

    chunk_a = MagicMock()
    chunk_a.embedding = [1.0, 0.0, 0.0]
    chunk_a.content = "alpha"
    chunk_b = MagicMock()
    chunk_b.embedding = [0.0, 1.0, 0.0]
    chunk_b.content = "beta"

    settings = MagicMock()
    settings.voyage_api_key = ""

    query_emb = [1.0, 0.0, 0.0]
    result = _rerank_chunks("alpha query", [chunk_a, chunk_b], query_emb, top_k=2, settings=settings)
    assert len(result) == 2
    # chunk_a should rank first (identical to query)
    assert result[0][0] is chunk_a


def test_rerank_chunks_respects_top_k():
    from ai_portal.rag.service import _rerank_chunks

    chunks = []
    for i in range(5):
        c = MagicMock()
        c.embedding = [float(i == 0), float(i == 1), float(i == 2)]
        c.content = f"chunk {i}"
        chunks.append(c)

    settings = MagicMock()
    settings.voyage_api_key = ""

    result = _rerank_chunks("q", chunks, [1.0, 0.0, 0.0], top_k=2, settings=settings)
    assert len(result) == 2


def test_rerank_chunks_voyage_path():
    """When voyage_api_key is set, the Voyage client is invoked."""
    from ai_portal.rag.service import _rerank_chunks

    chunk_a = MagicMock()
    chunk_a.content = "alpha"
    chunk_a.embedding = [1.0, 0.0]
    chunk_b = MagicMock()
    chunk_b.content = "beta"
    chunk_b.embedding = [0.0, 1.0]

    settings = MagicMock()
    settings.voyage_api_key = "voy-test-key"

    mock_result_obj_a = MagicMock()
    mock_result_obj_a.index = 0
    mock_result_obj_a.relevance_score = 0.95
    mock_result_obj_b = MagicMock()
    mock_result_obj_b.index = 1
    mock_result_obj_b.relevance_score = 0.80

    mock_rerank_result = MagicMock()
    mock_rerank_result.results = [mock_result_obj_a, mock_result_obj_b]

    with patch("ai_portal.rag.service.voyageai") as mock_voyage:
        mock_client = MagicMock()
        mock_voyage.Client.return_value = mock_client
        mock_client.rerank.return_value = mock_rerank_result

        result = _rerank_chunks("query", [chunk_a, chunk_b], [1.0, 0.0], top_k=2, settings=settings)

    assert len(result) == 2
    mock_client.rerank.assert_called_once()
    assert result[0][1] == 0.95


# ---------------------------------------------------------------------------
# search_knowledge_base_tool
# ---------------------------------------------------------------------------

def test_search_knowledge_base_tool_empty_kbs():
    """No KB IDs → empty result."""
    from ai_portal.rag.service import search_knowledge_base_tool

    db = MagicMock()
    result = search_knowledge_base_tool(db, query="hello", kb_ids=[])
    assert result["context"] == ""
    assert result["used_kbs"] == []
    assert result["citations"] == []


def test_search_knowledge_base_tool_returns_dict_shape():
    """Return dict always has context, used_kbs, citations keys."""
    from ai_portal.rag.service import search_knowledge_base_tool

    db = MagicMock()
    db.scalars.return_value = iter([])

    with patch("ai_portal.rag.service.embedding_svc") as mock_emb, \
         patch("ai_portal.rag.service.get_settings") as mock_gs:
        mock_emb.embed_texts.return_value = [[0.1] * 1024]
        s = MagicMock()
        s.rag_max_top_k = 30
        s.rag_min_top_k = 8
        s.rag_similarity_threshold = 0.3
        s.voyage_api_key = ""
        mock_gs.return_value = s

        result = search_knowledge_base_tool(db, query="test", kb_ids=[1])

    assert "context" in result
    assert "used_kbs" in result
    assert "citations" in result
