"""Test-only fake provider — returns canned LLMResponse/streams.

Gated behind ``GATEWAY_USE_FAKE_PROVIDER=true``. Enables smoke-testing the
gateway end-to-end (router → policies → trace/audit/usage emit) without any
real provider HTTP traffic or API keys.

Never load this in production.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TextBlock,
    Usage,
)


class FakeProvider:
    """Canned-response provider for smoke + integration tests.

    Returns a deterministic ``LLMResponse`` (or stream) with non-zero usage so
    the cost / trace / usage pipelines exercise their full code path.
    """

    name: str = "fake"
    capabilities: set[Capability] = {"chat", "streaming", "embeddings"}

    def __init__(self, *, text: str = "ok") -> None:
        self._text = text

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            id=f"fake-{uuid.uuid4().hex[:8]}",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text=self._text)],
            tool_calls=[],
            usage=Usage(input_tokens=7, output_tokens=3, total_tokens=10),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(
        self, req: LLMRequest
    ) -> AsyncIterator[StreamChunk]:
        for chunk in (
            {"type": "text_delta", "text": self._text},
            {
                "type": "usage",
                "input_tokens": 7,
                "output_tokens": 3,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
            },
            {"type": "iteration_complete", "stop_reason": "end_turn"},
        ):
            yield StreamChunk.model_validate(chunk)

    async def embed(self, texts: list[str], model: str) -> Embeddings:
        # Minimal embedding vector — only used if a caller exercises embed.
        return Embeddings(
            model=model,
            provider=self.name,
            vectors=[[0.0] * 8 for _ in texts],
            usage=Usage(input_tokens=sum(max(1, len(t) // 4) for t in texts)),
        )

    def count_tokens(self, text: str, model: str) -> int:
        return max(1, len(text) // 4)

    async def list_models(self):
        return []

    async def health(self):
        from ai_portal.gateway.types import HealthStatus

        return HealthStatus(healthy=True)


__all__ = ["FakeProvider"]
