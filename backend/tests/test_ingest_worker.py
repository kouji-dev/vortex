import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_portal.workers.ingest.worker import ingest_document_worker


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
        mock_emb.embed_texts.return_value = [[0.1] * 1024]
        result = ingest_document_worker(1, db=db)

    assert result is None
    assert doc.status == "ready"


def test_missing_document_returns_error(tmp_path):
    db = MagicMock()
    db.get.return_value = None

    result = ingest_document_worker(999, db=db)

    assert result == "Document not found"


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


def test_unsupported_file_type_returns_error(tmp_path):
    f = tmp_path / "file.xyz"
    f.write_bytes(b"data")
    doc = MagicMock()
    doc.filename = "file.xyz"
    doc.storage_path = str(f)
    doc.status = "pending"
    doc.chunks_done = 0
    doc.chunks_total = None
    db = MagicMock()
    db.get.return_value = doc

    result = ingest_document_worker(1, db=db)

    assert "Unsupported" in result
    assert doc.status == "failed"
