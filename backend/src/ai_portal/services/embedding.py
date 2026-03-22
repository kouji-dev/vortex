from __future__ import annotations

import httpx

from ai_portal.config import Settings, get_settings


def embed_texts(
    texts: list[str],
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[list[float]]:
    settings = settings or get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    url = f"{settings.openai_api_base.rstrip('/')}/embeddings"
    payload = {"model": settings.embedding_model, "input": texts}
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    close = client is None
    c = client or httpx.Client(timeout=120.0)
    try:
        r = c.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return [item["embedding"] for item in data["data"]]
    finally:
        if close:
            c.close()
