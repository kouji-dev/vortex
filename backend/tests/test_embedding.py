from unittest.mock import MagicMock, patch

from ai_portal.config import Settings
from ai_portal.services import embedding as embedding_svc


@patch("ai_portal.services.embedding.litellm.embedding")
def test_embed_texts_litellm(mock_embedding):
    fake = MagicMock()
    fake.data = [MagicMock(embedding=[0.1, 0.2])]
    mock_embedding.return_value = fake

    settings = Settings(
        llm_api_key="sk-test",
        llm_api_base="https://api.openai.com/v1",
        embedding_model="text-embedding-3-small",
    )
    out = embedding_svc.embed_texts(["hi"], settings=settings)

    assert out == [[0.1, 0.2]]
    mock_embedding.assert_called_once()
    call_kw = mock_embedding.call_args.kwargs
    assert call_kw["model"] == "text-embedding-3-small"
    assert call_kw["input"] == ["hi"]
    assert call_kw["api_key"] == "sk-test"
    assert call_kw["api_base"] == "https://api.openai.com/v1"
