from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_portal.workers.ingest.worker import (
    _mark_document_ready,
    _persist_document_failure,
    ingest_document_worker,
)


def _make_doc(tmp_path: Path, content: str = "Hello world. " * 50, filename: str = "test.txt"):
    f = tmp_path / filename
    f.write_text(content, encoding="utf-8")
    doc = MagicMock()
    doc.id = 1
    doc.filename = filename
    doc.storage_path = str(f)
    doc.status = "pending"
    doc.chunks_done = 0
    doc.chunks_total = None
    return doc, f


def test_successful_ingest_returns_none(tmp_path):
    doc, _ = _make_doc(tmp_path)
    db = MagicMock()
    db.get.return_value = doc

    with patch("ai_portal.workers.ingest.worker.embedding_svc") as mock_emb:
        mock_emb.embed_texts.side_effect = lambda texts: [[0.1] * 1024 for _ in texts]
        result = ingest_document_worker(1, db=db)

    assert result is None
    assert doc.status == "ready"


def test_missing_document_returns_error(tmp_path):
    db = MagicMock()
    db.get.return_value = None

    result = ingest_document_worker(999, db=db)

    assert result == "Document not found"
    db.commit.assert_not_called()


def test_missing_file_returns_error(tmp_path):
    doc = MagicMock()
    doc.filename = "missing.txt"
    doc.storage_path = str(tmp_path / "nonexistent.txt")
    doc.status = "pending"
    db = MagicMock()
    db.get.return_value = doc

    result = ingest_document_worker(1, db=db)

    assert result == "Stored file is missing"
    assert doc.status == "failed"
    db.commit.assert_called()


def test_unsupported_file_type_returns_error(tmp_path):
    f = tmp_path / "file.xyz"
    f.write_bytes(b"data")
    doc = MagicMock()
    doc.filename = "file.xyz"
    doc.storage_path = str(f)
    doc.status = "pending"
    doc.chunks_done = 0
    doc.chunks_total = None
    doc.ingest_error = None
    db = MagicMock()
    db.get.return_value = doc

    result = ingest_document_worker(1, db=db)

    assert "Unsupported" in result
    assert doc.status == "failed"
    assert doc.ingest_error


def test_embed_runtime_error_marks_failed_with_ingest_error(tmp_path):
    doc = MagicMock()
    doc.id = 1
    doc.filename = "note.txt"
    doc.storage_path = str(tmp_path / "note.txt")
    doc.status = "pending"
    doc.chunks_done = 0
    doc.chunks_total = None
    doc.ingest_error = None
    (tmp_path / "note.txt").write_text(
        "This is enough text to produce at least one semantic chunk for ingest. " * 8,
        encoding="utf-8",
    )
    db = MagicMock()
    db.get.return_value = doc

    with patch("ai_portal.workers.ingest.worker.embedding_svc") as mock_emb:
        mock_emb.embed_texts.side_effect = RuntimeError("voyage rate limit")
        result = ingest_document_worker(1, db=db)

    assert result == "Embedding request failed"
    assert doc.status == "failed"
    assert doc.ingest_error
    assert "rate limit" in doc.ingest_error.lower()


def test_embed_value_error_marks_failed(tmp_path):
    doc = MagicMock()
    doc.id = 1
    doc.filename = "note.txt"
    doc.storage_path = str(tmp_path / "note.txt")
    doc.status = "pending"
    doc.chunks_done = 0
    doc.chunks_total = None
    doc.ingest_error = None
    (tmp_path / "note.txt").write_text(
        "This is enough text to produce at least one semantic chunk for ingest. " * 8,
        encoding="utf-8",
    )
    db = MagicMock()
    db.get.return_value = doc

    with patch("ai_portal.workers.ingest.worker.embedding_svc") as mock_emb:
        mock_emb.embed_texts.side_effect = ValueError("No embedding credits")
        result = ingest_document_worker(1, db=db)

    assert result == "No embedding credits"
    assert doc.status == "failed"
    assert doc.ingest_error == "No embedding credits"


def test_persist_document_failure_truncates_message():
    db = MagicMock()
    row = MagicMock()
    row.status = "ingesting"
    row.ingest_error = None
    db.get.return_value = row

    long_msg = "x" * 9000
    _persist_document_failure(db, 5, long_msg)

    assert row.status == "failed"
    assert len(row.ingest_error) == 8192
    db.commit.assert_called()


def test_mark_document_ready_clears_ingest_error():
    db = MagicMock()
    row = MagicMock()
    row.status = "ingesting"
    row.ingest_error = "old"
    db.get.return_value = row

    _mark_document_ready(db, 3)

    assert row.status == "ready"
    assert row.ingest_error is None
    db.commit.assert_called()
