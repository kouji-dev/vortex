from unittest.mock import MagicMock
from ai_portal.knowledge_base.workers.ingest.progress import update_progress, set_chunks_total


def test_update_progress_sets_chunks_done():
    db = MagicMock()
    doc = MagicMock()
    doc.chunks_done = 0

    update_progress(db, doc, chunks_done=50)

    assert doc.chunks_done == 50
    db.commit.assert_called_once()


def test_set_chunks_total_sets_field():
    db = MagicMock()
    doc = MagicMock()

    set_chunks_total(db, doc, total=200)

    assert doc.chunks_total == 200
    db.commit.assert_called_once()
