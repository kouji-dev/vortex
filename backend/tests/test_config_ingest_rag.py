from ai_portal.config import Settings


def test_ingest_defaults():
    s = Settings()
    assert s.kb_max_file_size_mb == 500
    assert s.ingest_commit_batch_size == 100
    assert s.ingest_embed_batch_size == 128


def test_rag_defaults():
    s = Settings()
    assert s.rag_max_top_k == 30
    assert s.rag_min_top_k == 8
    assert s.rag_similarity_threshold == 0.3
    assert s.rag_max_tool_iterations == 1


def test_ingest_env_override(monkeypatch):
    monkeypatch.setenv("KB_MAX_FILE_SIZE_MB", "200")
    s = Settings()
    assert s.kb_max_file_size_mb == 200
