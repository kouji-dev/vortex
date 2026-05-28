"""K1: Public gateway facade.

The facade in ``ai_portal.gateway.facade`` (re-exported from
``ai_portal.gateway``) is the unified entry point used by other modules
(chat, RAG, memories, workers). It composes routing + cache + budget +
cost + trace persistence around the provider call.

Surface (per spec):

- ``complete(req, actor) -> LLMResponse``
- ``stream(req, actor) -> AsyncIterator[StreamChunk]``
- ``embed(texts, model, actor) -> Embeddings``
- ``rerank(query, docs, model, actor) -> list[RerankResult]``
- ``count_tokens(text, model) -> int``
- ``estimate_cost(req, model) -> cents``
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest

from ai_portal import gateway
from ai_portal.gateway.facade import (
    Actor,
    FacadeConfig,
    GatewayFacade,
    set_default_facade,
)
from ai_portal.gateway.pricing import PricingSnapshot
from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    LLMRequest,
    LLMResponse,
    Message,
    StreamChunk,
    TextBlock,
    Usage,
)

pytestmark = pytest.mark.asyncio


# ── stubs ────────────────────────────────────────────────────────────────


class _StubProvider:
    name = "stub"
    capabilities: set[Capability] = {"chat", "embeddings"}

    def __init__(self) -> None:
        self.complete_calls = 0
        self.stream_calls = 0
        self.embed_calls = 0

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        self.complete_calls += 1
        return LLMResponse(
            id=f"resp_{self.complete_calls}",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text="ok")],
            tool_calls=[],
            usage=Usage(input_tokens=1000, output_tokens=500),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(
        self, req: LLMRequest
    ) -> AsyncIterator[StreamChunk]:
        self.stream_calls += 1
        yield StreamChunk.model_validate({"type": "text_delta", "text": "hi"})
        yield StreamChunk.model_validate(
            {"type": "usage", "input_tokens": 3, "output_tokens": 2}
        )
        yield StreamChunk.model_validate(
            {"type": "iteration_complete", "stop_reason": "end_turn"}
        )

    async def embed(self, texts: list[str], model: str) -> Embeddings:
        self.embed_calls += 1
        return Embeddings(
            model=model,
            provider=self.name,
            vectors=[[0.1, 0.2, 0.3] for _ in texts],
            usage=Usage(input_tokens=len(texts), output_tokens=0),
        )

    def count_tokens(self, text: str, model: str) -> int:
        return max(1, len(text) // 4)


class _StubReranker:
    name = "stub-rerank"

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_k: int | None = None,
        model: str | None = None,
        return_documents: bool = False,
    ):
        from ai_portal.gateway.rerank.protocol import RerankResult

        out = [
            RerankResult(
                index=i,
                relevance_score=1.0 - (i * 0.1),
                document=doc if return_documents else None,
            )
            for i, doc in enumerate(documents)
        ]
        return out[: top_k or len(documents)]


def _make_actor(org_id: uuid.UUID | None = None) -> Actor:
    return Actor(
        org_id=org_id or uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        user_id=42,
        kind="user",
    )


def _make_req(text: str = "hello", model: str = "stub:m") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[Message(role="user", content=[TextBlock(text=text)])],
    )


def _make_facade(
    provider: _StubProvider | None = None,
    *,
    pricing: PricingSnapshot | None = None,
    reranker: _StubReranker | None = None,
    audit_sink: list[dict] | None = None,
    usage_sink: list[dict] | None = None,
    trace_sink: list[dict] | None = None,
) -> tuple[GatewayFacade, _StubProvider]:
    prov = provider or _StubProvider()
    audit_sink = audit_sink if audit_sink is not None else []
    usage_sink = usage_sink if usage_sink is not None else []
    trace_sink = trace_sink if trace_sink is not None else []

    def resolve_provider(req: LLMRequest, actor: Actor):  # noqa: ARG001
        return prov

    def resolve_pricing(model: str):  # noqa: ARG001
        return pricing

    def emit_audit_stub(**kw):
        audit_sink.append(kw)

    def emit_usage_stub(**kw):
        usage_sink.append(kw)

    def emit_trace_stub(record):
        trace_sink.append(record)

    cfg = FacadeConfig(
        resolve_provider=resolve_provider,
        resolve_pricing=resolve_pricing,
        resolve_reranker=lambda model: reranker,  # noqa: ARG005
        emit_audit=emit_audit_stub,
        emit_usage=emit_usage_stub,
        emit_trace=emit_trace_stub,
    )
    facade = GatewayFacade(cfg)
    facade._audit_sink = audit_sink  # type: ignore[attr-defined]
    facade._usage_sink = usage_sink  # type: ignore[attr-defined]
    facade._trace_sink = trace_sink  # type: ignore[attr-defined]
    return facade, prov


# ── tests ─────────────────────────────────────────────────────────────────


async def test_facade_complete_invokes_provider_and_returns_canonical_response() -> None:
    facade, provider = _make_facade()
    actor = _make_actor()
    resp = await facade.complete(_make_req(), actor)
    assert provider.complete_calls == 1
    assert isinstance(resp, LLMResponse)
    assert resp.content[0].text == "ok"  # type: ignore[union-attr]


async def test_facade_complete_writes_trace_audit_and_usage() -> None:
    pricing = PricingSnapshot(
        price_input_per_1k_cents=30,
        price_output_per_1k_cents=60,
        price_cache_read_per_1k_cents=3,
    )
    audit, usage, trace = [], [], []
    facade, _ = _make_facade(
        pricing=pricing,
        audit_sink=audit,
        usage_sink=usage,
        trace_sink=trace,
    )
    actor = _make_actor()

    await facade.complete(_make_req(), actor)

    assert len(trace) == 1
    rec = trace[0]
    assert rec.tokens_in == 1000
    assert rec.tokens_out == 500
    assert rec.status == "ok"
    assert rec.cost_cents == pytest.approx(60.0)
    assert rec.model_used == "stub:m"

    # Audit fired once with the canonical event.
    assert any(c["event_type"] == "gateway.completion" for c in audit)
    # Usage fired for tokens_in + tokens_out.
    units = [c["unit"] for c in usage]
    assert "tokens_in" in units
    assert "tokens_out" in units


async def test_facade_stream_yields_chunks_and_writes_trace() -> None:
    audit, usage, trace = [], [], []
    facade, provider = _make_facade(
        audit_sink=audit, usage_sink=usage, trace_sink=trace
    )
    actor = _make_actor()

    chunks: list = []
    async for ch in facade.stream(_make_req(), actor):
        chunks.append(ch)

    assert provider.stream_calls == 1
    # text_delta + usage + iteration_complete = 3 chunks pass through.
    assert len(chunks) == 3
    # Trace flushed once at end of stream.
    assert len(trace) == 1
    rec = trace[0]
    assert rec.tokens_in == 3
    assert rec.tokens_out == 2
    # Audit fired for the streamed completion.
    assert any(c["event_type"] == "gateway.completion" for c in audit)


async def test_facade_embed_returns_vectors_and_audits() -> None:
    audit: list[dict] = []
    facade, provider = _make_facade(audit_sink=audit)
    actor = _make_actor()
    res = await facade.embed(["a", "b"], model="emb-1", actor=actor)
    assert provider.embed_calls == 1
    assert len(res.vectors) == 2
    assert any(c["event_type"] == "gateway.embedding" for c in audit)


async def test_facade_rerank_returns_sorted_and_audits() -> None:
    audit: list[dict] = []
    rer = _StubReranker()
    facade, _ = _make_facade(reranker=rer, audit_sink=audit)
    actor = _make_actor()
    res = await facade.rerank(
        query="q", documents=["a", "b", "c"], model="rer-1", actor=actor
    )
    assert len(res) == 3
    assert res[0].relevance_score >= res[-1].relevance_score
    assert any(c["event_type"] == "gateway.rerank" for c in audit)


async def test_facade_count_tokens_delegates_to_provider() -> None:
    facade, _ = _make_facade()
    n = facade.count_tokens("hello world", model="stub:m")
    assert n >= 1


async def test_facade_estimate_cost_uses_pricing_and_message_length() -> None:
    pricing = PricingSnapshot(
        price_input_per_1k_cents=30,
        price_output_per_1k_cents=60,
        price_cache_read_per_1k_cents=3,
    )
    facade, _ = _make_facade(pricing=pricing)
    cost = facade.estimate_cost(_make_req("x" * 4000), model="stub:m")
    # token est ~ 1000 chars / 4 = 1000 tokens at 30 cents/1k = 30
    assert cost == pytest.approx(30.0, rel=0.1)


async def test_facade_complete_records_trace_on_provider_error() -> None:
    class _BoomProvider(_StubProvider):
        async def complete_canonical(self, req: LLMRequest) -> LLMResponse:  # noqa: ARG002
            raise RuntimeError("boom")

    audit, usage, trace = [], [], []
    facade, _ = _make_facade(
        provider=_BoomProvider(),
        audit_sink=audit,
        usage_sink=usage,
        trace_sink=trace,
    )
    actor = _make_actor()
    with pytest.raises(RuntimeError):
        await facade.complete(_make_req(), actor)
    # Trace must still be written with status=error.
    assert len(trace) == 1
    assert trace[0].status == "error"
    assert trace[0].error and "boom" in trace[0].error


async def test_module_level_complete_uses_default_facade() -> None:
    facade, provider = _make_facade()
    actor = _make_actor()
    token = set_default_facade(facade)
    try:
        resp = await gateway.complete(_make_req(), actor)
        assert provider.complete_calls == 1
        assert resp.content[0].text == "ok"  # type: ignore[union-attr]
    finally:
        set_default_facade(token)


async def test_module_level_stream_uses_default_facade() -> None:
    facade, provider = _make_facade()
    actor = _make_actor()
    token = set_default_facade(facade)
    try:
        chunks: list = []
        async for ch in gateway.stream(_make_req(), actor):
            chunks.append(ch)
        assert provider.stream_calls == 1
        assert len(chunks) == 3
    finally:
        set_default_facade(token)
