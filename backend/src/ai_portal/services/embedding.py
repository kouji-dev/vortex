from __future__ import annotations

import litellm

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

    resp = litellm.embedding(
        model=settings.embedding_model.strip(),
        input=texts,
        api_key=settings.llm_api_key,
        api_base=normalize_openai_compatible_base(settings.llm_api_base),
    )
    if isinstance(resp, dict):
        rows = resp["data"]
        return [r["embedding"] for r in rows]
    return [item.embedding for item in resp.data]
