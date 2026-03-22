"""RAG retrieval is covered indirectly via chat + ingest in integration tests."""

from tests.conftest import requires_postgres


@requires_postgres
def test_rag_module_importable():
    from ai_portal.services import rag as rag_mod

    assert rag_mod.retrieve_context is not None
