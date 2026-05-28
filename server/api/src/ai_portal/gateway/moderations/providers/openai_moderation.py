"""OpenAI moderation — ``POST https://api.openai.com/v1/moderations``.

Wire shape::

    POST /v1/moderations
    {"input": "...", "model": "omni-moderation-latest"}

Response::

    {"id": "...", "model": "...",
     "results": [{"flagged": bool, "categories": {...}, "category_scores": {...}}]}

We pass ``input`` as a list of strings — OpenAI accepts batched input.
"""

from __future__ import annotations

import httpx

from ai_portal.gateway.moderations.protocol import (
    CATEGORIES,
    ModerationResult,
)

OPENAI_DEFAULT_MOD_MODEL = "omni-moderation-latest"


class OpenAIModerator:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com",
        default_model: str = OPENAI_DEFAULT_MOD_MODEL,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout = timeout_seconds

    async def moderate(
        self, inputs: list[str], *, model: str | None = None
    ) -> list[ModerationResult]:
        if not inputs:
            return []
        body = {"input": inputs, "model": model or self._default_model}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/v1/moderations",
                json=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("results", []):
            cats_in = r.get("categories") or {}
            scores_in = r.get("category_scores") or {}
            cats = {c: bool(cats_in.get(c, False)) for c in CATEGORIES}
            scores = {c: float(scores_in.get(c, 0.0)) for c in CATEGORIES}
            results.append(
                ModerationResult(
                    flagged=bool(r.get("flagged", False)),
                    categories=cats,
                    category_scores=scores,
                )
            )
        return results


__all__ = ["OpenAIModerator", "OPENAI_DEFAULT_MOD_MODEL"]
