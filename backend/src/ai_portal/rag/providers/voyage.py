from __future__ import annotations

from typing import Literal

from ai_portal.core.config import Settings, get_settings
from ai_portal.catalog.providers.routing import normalize_openai_compatible_base

# Voyage allows many texts per request; batch for memory / timeouts on large docs.
_VOYAGE_EMBED_BATCH = 128

# Lowest-cost current-gen Voyage **text** embedding per
# https://docs.voyageai.com/docs/pricing ($0.02/M tokens; 200M free/month for this model).
# Larger models (e.g. voyage-4, voyage-4-large) cost more per token.
VOYAGE_DEFAULT_EMBEDDING_MODEL = "voyage-4-lite"


def embeddings_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.voyage_api_key.strip()) or bool(s.openai_api_key.strip())


def embeddings_missing_key_message() -> str:
    return (
        "Set VOYAGE_API_KEY for Voyage embeddings (recommended), or OPENAI_API_KEY for "
        "OpenAI-compatible embeddings (with OPENAI_API_BASE and EMBEDDING_MODEL). "
        "Chat-only ANTHROPIC_API_KEY does not provide embeddings."
    )


def _embed_openai(
    texts: list[str],
    *,
    settings: Settings,
) -> list[list[float]]:
    from langchain_openai import OpenAIEmbeddings  # pylint: disable=import-error

    model = (settings.embedding_model or "").strip() or "text-embedding-3-small"
    base_url = normalize_openai_compatible_base(settings.openai_api_base)
    # Match pgvector column (1024) and Voyage-sized vectors for mixed / migrated DBs.
    kwargs: dict = {}
    if "text-embedding-3" in model:
        kwargs["dimensions"] = 1024
    emb = OpenAIEmbeddings(
        model=model,
        api_key=settings.openai_api_key,
        base_url=base_url,
        **kwargs,
    )
    return emb.embed_documents(texts)


def _embed_voyage(
    texts: list[str],
    *,
    input_type: Literal["document", "query"],
    settings: Settings,
) -> list[list[float]]:
    from voyageai import Client  # pylint: disable=import-error

    model = (settings.embedding_model or "").strip() or VOYAGE_DEFAULT_EMBEDDING_MODEL
    client = Client(api_key=settings.voyage_api_key)
    out: list[list[float]] = []
    for i in range(0, len(texts), _VOYAGE_EMBED_BATCH):
        batch = texts[i : i + _VOYAGE_EMBED_BATCH]
        result = client.embed(batch, model=model, input_type=input_type)
        out.extend(result.embeddings)
    return out


def embed_texts(
    texts: list[str],
    *,
    input_type: Literal["document", "query"] = "document",
    settings: Settings | None = None,
) -> list[list[float]]:
    """Embed texts for ingest (``document``) or RAG query (``query``).

    Uses **Voyage** when ``VOYAGE_API_KEY`` is set; otherwise OpenAI-compatible
    ``OpenAIEmbeddings`` when ``OPENAI_API_KEY`` is set.
    """
    settings = settings or get_settings()
    if settings.voyage_api_key.strip():
        return _embed_voyage(texts, input_type=input_type, settings=settings)
    if settings.openai_api_key.strip():
        return _embed_openai(texts, settings=settings)
    raise ValueError(embeddings_missing_key_message())
