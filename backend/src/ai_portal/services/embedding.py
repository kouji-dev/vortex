from __future__ import annotations

from ai_portal.config import Settings, get_settings
from ai_portal.services.llm_connect import normalize_openai_compatible_base


def embed_texts(
    texts: list[str],
    *,
    settings: Settings | None = None,
) -> list[list[float]]:
    settings = settings or get_settings()
    if not settings.llm_api_key.strip():
        raise ValueError("LLM_API_KEY (or OPENAI_API_KEY) is not set")

    # Lazy import: keeps startup light; optional dep must be installed (see pyproject).
    from langchain_openai import OpenAIEmbeddings  # pylint: disable=import-error

    emb = OpenAIEmbeddings(
        model=settings.embedding_model.strip(),
        api_key=settings.llm_api_key,
        base_url=normalize_openai_compatible_base(settings.llm_api_base),
    )
    return emb.embed_documents(texts)
