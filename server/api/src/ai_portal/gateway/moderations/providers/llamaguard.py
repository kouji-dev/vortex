"""LlamaGuard moderation — self-hosted via OpenAI-compatible chat endpoint.

LlamaGuard is a Meta safeguards model. When served behind vllm / llama.cpp
/ ollama with the OpenAI-compatible surface, the model responds with::

    safe
    -- OR --
    unsafe
    S1,S5,S7

where ``S1..Sn`` are MLCommons taxonomy category codes. We translate them
into OpenAI's moderation category names so downstream consumers see a
uniform shape.
"""

from __future__ import annotations

import httpx

from ai_portal.gateway.moderations.protocol import (
    CATEGORIES,
    ModerationResult,
)

LLAMAGUARD_DEFAULT_MODEL = "meta-llama/Llama-Guard-3-8B"

# MLCommons taxonomy codes used by LlamaGuard-3 → our category names.
# Categories without a clean mapping fall back to "harassment".
_S_CODE_TO_CATEGORY: dict[str, str] = {
    "S1": "violence",  # Violent Crimes
    "S2": "violence",  # Non-Violent Crimes (closest)
    "S3": "sexual",  # Sex Crimes
    "S4": "sexual/minors",  # Child Sexual Exploitation
    "S5": "harassment",  # Defamation
    "S6": "self-harm",  # Specialized Advice (often self-harm)
    "S7": "harassment",  # Privacy
    "S8": "hate",  # Intellectual Property → fallback hate (rare)
    "S9": "violence/graphic",  # Indiscriminate Weapons
    "S10": "hate",  # Hate
    "S11": "self-harm",  # Suicide & Self-Harm
    "S12": "sexual",  # Sexual Content
    "S13": "hate",  # Elections → fallback
    "S14": "violence",  # Code Interpreter Abuse → fallback
}


def _parse_llamaguard_text(text: str) -> tuple[bool, set[str]]:
    """Parse LlamaGuard's chat output → (flagged, set of category names)."""
    if not text:
        return False, set()
    stripped = text.strip().lower()
    if stripped.startswith("safe") and not stripped.startswith("unsafe"):
        return False, set()
    if not stripped.startswith("unsafe"):
        return False, set()
    # Find next non-empty line, split codes by comma or whitespace.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    codes: list[str] = []
    if len(lines) >= 2:
        for token in lines[1].replace(",", " ").split():
            token = token.strip().upper()
            if token.startswith("S") and token[1:].isdigit():
                codes.append(token)
    mapped = {
        _S_CODE_TO_CATEGORY[c] for c in codes if c in _S_CODE_TO_CATEGORY
    }
    return True, mapped


class LlamaGuardModerator:
    """Self-hosted LlamaGuard via OpenAI-compatible chat completions."""

    name = "llamaguard"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        default_model: str = LLAMAGUARD_DEFAULT_MODEL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout_seconds

    async def moderate(
        self, inputs: list[str], *, model: str | None = None
    ) -> list[ModerationResult]:
        out: list[ModerationResult] = []
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        mdl = model or self._default_model

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for text in inputs:
                body = {
                    "model": mdl,
                    "messages": [{"role": "user", "content": text}],
                }
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                content = (
                    (data.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                flagged, names = _parse_llamaguard_text(content)
                cats = {c: (c in names) for c in CATEGORIES}
                scores = {c: (1.0 if cats[c] else 0.0) for c in CATEGORIES}
                out.append(
                    ModerationResult(
                        flagged=flagged, categories=cats, category_scores=scores
                    )
                )
        return out


__all__ = ["LlamaGuardModerator", "LLAMAGUARD_DEFAULT_MODEL"]
