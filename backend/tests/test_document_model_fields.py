from ai_portal.knowledge_base.model import Document, DocumentChunk


def test_document_has_progress_fields():
    d = Document()
    assert hasattr(d, "chunks_total")
    assert hasattr(d, "chunks_done")


def test_document_chunk_has_search_vector():
    c = DocumentChunk()
    assert hasattr(c, "search_vector")
