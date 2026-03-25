from unittest.mock import MagicMock, patch

from ai_portal.config import Settings
from ai_portal.services import embedding as embedding_svc


@patch("langchain_openai.OpenAIEmbeddings")
def test_embed_texts_openai_embeddings(mock_embeddings_cls):
    instance = MagicMock()
    instance.embed_documents.return_value = [[0.1, 0.2]]
    mock_embeddings_cls.return_value = instance

    settings = Settings(
        llm_api_key="sk-test",
        llm_api_base="https://api.openai.com/v1",
        embedding_model="text-embedding-3-small",
    )
    out = embedding_svc.embed_texts(["hi"], settings=settings)

    assert out == [[0.1, 0.2]]
    mock_embeddings_cls.assert_called_once()
    call_kw = mock_embeddings_cls.call_args.kwargs
    assert call_kw["model"] == "text-embedding-3-small"
    assert call_kw["api_key"] == "sk-test"
    assert call_kw["base_url"] == "https://api.openai.com/v1"
    instance.embed_documents.assert_called_once_with(["hi"])
