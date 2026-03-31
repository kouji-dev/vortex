from unittest.mock import MagicMock, patch

from ai_portal.config import Settings
from ai_portal.services import embedding as embedding_svc


@patch("langchain_openai.OpenAIEmbeddings")
def test_embed_texts_openai_embeddings(mock_embeddings_cls):
    instance = MagicMock()
    instance.embed_documents.return_value = [[0.1, 0.2]]
    mock_embeddings_cls.return_value = instance

    settings = Settings(
        voyage_api_key="",
        openai_api_key="sk-test",
        openai_api_base="https://api.openai.com/v1",
        embedding_model="text-embedding-3-small",
    )
    out = embedding_svc.embed_texts(["hi"], settings=settings)

    assert out == [[0.1, 0.2]]
    mock_embeddings_cls.assert_called_once()
    call_kw = mock_embeddings_cls.call_args.kwargs
    assert call_kw["model"] == "text-embedding-3-small"
    assert call_kw["api_key"] == "sk-test"
    assert call_kw["base_url"] == "https://api.openai.com/v1"
    assert call_kw["dimensions"] == 1024
    instance.embed_documents.assert_called_once_with(["hi"])


@patch("voyageai.Client")
def test_embed_texts_voyage_uses_default_lite_when_model_unset(mock_client_cls):
    mock_result = MagicMock()
    mock_result.embeddings = [[0.1]]
    instance = MagicMock()
    instance.embed.return_value = mock_result
    mock_client_cls.return_value = instance

    settings = Settings(voyage_api_key="vo-test", embedding_model="")
    embedding_svc.embed_texts(["x"], settings=settings)

    assert (
        instance.embed.call_args.kwargs["model"]
        == embedding_svc.VOYAGE_DEFAULT_EMBEDDING_MODEL
    )
    assert embedding_svc.VOYAGE_DEFAULT_EMBEDDING_MODEL == "voyage-4-lite"


@patch("voyageai.Client")
def test_embed_texts_voyage_prefers_voyage_when_key_set(mock_client_cls):
    mock_result = MagicMock()
    mock_result.embeddings = [[0.3, 0.4]]
    instance = MagicMock()
    instance.embed.return_value = mock_result
    mock_client_cls.return_value = instance

    settings = Settings(
        voyage_api_key="vo-test",
        embedding_model="voyage-4-lite",
    )
    out = embedding_svc.embed_texts(["chunk"], input_type="document", settings=settings)

    assert out == [[0.3, 0.4]]
    mock_client_cls.assert_called_once_with(api_key="vo-test")
    instance.embed.assert_called_once_with(
        ["chunk"],
        model="voyage-4-lite",
        input_type="document",
    )
