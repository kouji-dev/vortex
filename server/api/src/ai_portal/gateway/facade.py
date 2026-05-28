"""Gateway facade — single entry point for internal callers.

Other modules (chat, RAG, memories, workers) call this facade instead of
talking to providers directly. It composes the cross-cutting concerns:

- **routing** → :func:`FacadeConfig.resolve_provider`
- **cache + budget + cost** → :func:`ai_portal.gateway.policies.complete_with_policies`
- **trace** → :func:`FacadeConfig.emit_trace`
- **audit** + **usage** → :func:`FacadeConfig.emit_audit` / ``emit_usage``

The facade is provider-agnostic; resolution and policy hooks are injected
via :class:`FacadeConfig`. Production wiring lives in ``main.py`` startup;
tests build a facade with stubbed hooks.

Public surface (mirrored at the package root ``ai_portal.gateway``):

- :func:`complete`        — non-streaming completion
- :func:`stream`          — streaming completion
- :func:`embed`           — embeddings
- :func:`rerank`          — re-rank docs against a query
- :func:`count_tokens`    — provider token count
- :func:`estimate_cost`   — pre-call cost estimate in cents
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ai_portal.gateway.policies import complete_with_policies
from ai_portal.gateway.pricing import PricingSnapshot, compute_cost_cents
from ai_portal.gateway.traces.writer import TraceRecord
from ai_portal.gateway.types import (
    Embeddings,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    Usage,
)

logger = logging.getLogger(__name__)


# ── actor ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Actor:
    """Caller identity passed into every facade method.

    Routed straight into audit / usage / trace rows so cross-module calls
    keep a unified actor shape (mirrors :class:`control_plane.Actor`).
    """

    org_id: uuid.UUID
    user_id: int | None = None
    kind: str = "user"  # "user" | "service" | "api_key"
    api_key_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "org_id": str(self.org_id),
            "user_id": self.user_id,
            "kind": self.kind,
            "api_key_id": self.api_key_id,
        }


# ── config protocol ──────────────────────────────────────────────────────


class _ProviderLike(Protocol):
    name: str
    capabilities: set

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse: ...
    async def stream_canonical(self, req: LLMRequest) -> AsyncIterator[StreamChunk]: ...
    async def embed(self, texts: list[str], model: str) -> Embeddings: ...


class _RerankerLike(Protocol):
    name: str

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_k: int | None = None,
        model: str | None = None,
        return_documents: bool = False,
    ) -> list[Any]: ...


ResolveProvider = Callable[[LLMRequest, Actor], _ProviderLike]
ResolvePricing = Callable[[str], PricingSnapshot | None]
ResolveReranker = Callable[[str], _RerankerLike | None]
EmitTrace = Callable[[TraceRecord], None]
EmitAudit = Callable[..., None]
EmitUsage = Callable[..., None]


@dataclass(slots=True)
class FacadeConfig:
    """Injected dependencies for the facade.

    All hooks are optional. The default no-op implementations keep the
    facade usable in unit tests without DB wiring.
    """

    resolve_provider: ResolveProvider
    resolve_pricing: ResolvePricing = field(default=lambda _model: None)
    resolve_reranker: ResolveReranker = field(default=lambda _model: None)
    emit_audit: EmitAudit = field(default=lambda **_kw: None)
    emit_usage: EmitUsage = field(default=lambda **_kw: None)
    emit_trace: EmitTrace = field(default=lambda _rec: None)
    route_name: str = "internal.facade"


# ── facade ───────────────────────────────────────────────────────────────


class GatewayFacade:
    """Composes routing + policies + observability for internal callers."""

    def __init__(self, cfg: FacadeConfig) -> None:
        self.cfg = cfg

    # ── completions ─────────────────────────────────────────────────────

    async def complete(self, req: LLMRequest, actor: Actor) -> LLMResponse:
        """Non-streaming completion with full policy + observability stack."""
        provider = self.cfg.resolve_provider(req, actor)
        pricing = self.cfg.resolve_pricing(req.model)
        started = time.monotonic()
        status = "ok"
        error: str | None = None
        usage = Usage()
        cost_cents = 0.0
        model_used = req.model
        provider_name = getattr(provider, "name", "unknown")
        resp: LLMResponse | None = None

        try:
            result = await complete_with_policies(req, provider, pricing=pricing)
            resp = result.response
            usage = resp.usage
            cost_cents = result.cost_cents
            model_used = resp.model_used or req.model
            provider_name = resp.provider or provider_name
            return resp
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = str(exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - started) * 1000)
            self._record(
                actor=actor,
                req=req,
                model_used=model_used,
                provider_name=provider_name,
                status=status,
                latency_ms=latency_ms,
                usage=usage,
                cost_cents=cost_cents,
                error=error,
                event_type="gateway.completion",
            )

    async def stream(
        self, req: LLMRequest, actor: Actor
    ) -> AsyncIterator[StreamChunk]:
        """Streaming completion. Trace + audit fire when the stream closes."""
        provider = self.cfg.resolve_provider(req, actor)
        pricing = self.cfg.resolve_pricing(req.model)
        started = time.monotonic()
        status = "ok"
        error: str | None = None
        tokens_in = tokens_out = 0
        tokens_cache_read = tokens_cache_write = 0
        model_used = req.model
        provider_name = getattr(provider, "name", "unknown")

        try:
            async for chunk in provider.stream_canonical(req):
                # Extract usage stats from the inner discriminated chunk.
                inner = chunk.root if hasattr(chunk, "root") else chunk
                kind = getattr(inner, "type", None)
                if kind == "usage":
                    tokens_in = getattr(inner, "input_tokens", 0) or tokens_in
                    tokens_out = getattr(inner, "output_tokens", 0) or tokens_out
                    tokens_cache_read = (
                        getattr(inner, "cache_read_tokens", 0) or tokens_cache_read
                    )
                    tokens_cache_write = (
                        getattr(inner, "cache_write_tokens", 0) or tokens_cache_write
                    )
                yield chunk
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = str(exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - started) * 1000)
            usage = Usage(
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                cache_read_tokens=tokens_cache_read,
                cache_write_tokens=tokens_cache_write,
            )
            cost_cents = compute_cost_cents(usage, pricing) if pricing else 0.0
            self._record(
                actor=actor,
                req=req,
                model_used=model_used,
                provider_name=provider_name,
                status=status,
                latency_ms=latency_ms,
                usage=usage,
                cost_cents=cost_cents,
                error=error,
                event_type="gateway.completion",
            )

    # ── embeddings ──────────────────────────────────────────────────────

    async def embed(
        self, texts: list[str], *, model: str, actor: Actor
    ) -> Embeddings:
        """Embed texts via the provider for ``model``."""
        # Build a stub request so resolve_provider can pick on model + capabilities.
        req = LLMRequest(model=model, messages=[])
        provider = self.cfg.resolve_provider(req, actor)
        try:
            result = await provider.embed(texts, model)
            self._safe_audit(
                event_type="gateway.embedding",
                actor=actor,
                payload={
                    "model": model,
                    "n_texts": len(texts),
                    "input_tokens": result.usage.input_tokens,
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001
            self._safe_audit(
                event_type="gateway.embedding",
                actor=actor,
                payload={"model": model, "n_texts": len(texts), "error": str(exc)},
            )
            raise

    # ── rerank ──────────────────────────────────────────────────────────

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        model: str,
        actor: Actor,
        top_k: int | None = None,
        return_documents: bool = False,
    ) -> list[Any]:
        """Rerank docs against ``query`` using the model's reranker."""
        reranker = self.cfg.resolve_reranker(model)
        if reranker is None:
            raise RuntimeError(f"no reranker bound for model {model!r}")
        try:
            results = await reranker.rerank(
                query=query,
                documents=documents,
                top_k=top_k,
                model=model,
                return_documents=return_documents,
            )
            self._safe_audit(
                event_type="gateway.rerank",
                actor=actor,
                payload={
                    "model": model,
                    "n_docs": len(documents),
                    "top_k": top_k,
                },
            )
            return results
        except Exception as exc:  # noqa: BLE001
            self._safe_audit(
                event_type="gateway.rerank",
                actor=actor,
                payload={
                    "model": model,
                    "n_docs": len(documents),
                    "error": str(exc),
                },
            )
            raise

    # ── token + cost helpers ────────────────────────────────────────────

    def count_tokens(self, text: str, *, model: str) -> int:
        """Provider-side token count (best-effort heuristic when unbound)."""
        req = LLMRequest(model=model, messages=[])
        actor = Actor(
            org_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            user_id=None,
            kind="service",
        )
        try:
            provider = self.cfg.resolve_provider(req, actor)
        except Exception:  # noqa: BLE001
            provider = None
        if provider is not None and hasattr(provider, "count_tokens"):
            try:
                return int(provider.count_tokens(text, model))
            except Exception:  # noqa: BLE001
                pass
        # Fallback heuristic: ~4 chars per token.
        return max(1, len(text) // 4)

    def estimate_cost(self, req: LLMRequest, *, model: str) -> float:
        """Estimate cents for ``req`` using pricing snapshot for ``model``.

        Output tokens are assumed equal to ``req.max_tokens`` when set, else
        a conservative 0 (input-only estimate). Cache reads default to 0.
        """
        pricing = self.cfg.resolve_pricing(model)
        if pricing is None:
            return 0.0
        # Count input tokens across all message text blocks.
        n_in = 0
        for msg in req.messages:
            for block in msg.content:
                txt = getattr(block, "text", None)
                if txt:
                    n_in += self.count_tokens(txt, model=model)
        n_out = req.max_tokens or 0
        usage = Usage(input_tokens=n_in, output_tokens=n_out)
        return compute_cost_cents(usage, pricing)

    # ── observability emit (public — also called by compat routes) ──────

    def record_call(
        self,
        *,
        actor: Actor,
        req: LLMRequest,
        model_used: str,
        provider_name: str,
        status: str,
        latency_ms: int,
        usage: Usage,
        cost_cents: float,
        error: str | None = None,
        event_type: str = "gateway.completion",
    ) -> None:
        """Public entry-point to fire trace + audit + usage for one call.

        Compat surfaces (OpenAI/Anthropic/Bedrock) that don't go through
        :func:`complete` (they call :func:`complete_with_policies` directly
        with their own provider dep) use this to keep observability wired.
        """
        self._record(
            actor=actor,
            req=req,
            model_used=model_used,
            provider_name=provider_name,
            status=status,
            latency_ms=latency_ms,
            usage=usage,
            cost_cents=cost_cents,
            error=error,
            event_type=event_type,
        )

    # ── internals ───────────────────────────────────────────────────────

    def _record(
        self,
        *,
        actor: Actor,
        req: LLMRequest,
        model_used: str,
        provider_name: str,
        status: str,
        latency_ms: int,
        usage: Usage,
        cost_cents: float,
        error: str | None,
        event_type: str,
    ) -> None:
        """Write trace + audit + usage for one completed call. Best-effort."""
        try:
            rec = TraceRecord(
                org_id=actor.org_id,
                route=self.cfg.route_name,
                actor_json=actor.to_dict(),
                model_requested=req.model,
                model_used=model_used,
                provider=provider_name,
                status=status,
                latency_ms=latency_ms,
                tokens_in=usage.input_tokens,
                tokens_out=usage.output_tokens,
                tokens_cache_read=usage.cache_read_tokens,
                tokens_cache_write=usage.cache_write_tokens,
                cost_cents=cost_cents,
                cache_hit=False,
                error=error,
            )
            self.cfg.emit_trace(rec)
        except Exception:  # noqa: BLE001
            logger.exception("facade._record: emit_trace failed")

        self._safe_audit(
            event_type=event_type,
            actor=actor,
            payload={
                "model_requested": req.model,
                "model_used": model_used,
                "provider": provider_name,
                "status": status,
                "latency_ms": latency_ms,
                "tokens_in": usage.input_tokens,
                "tokens_out": usage.output_tokens,
                "cost_cents": cost_cents,
                "error": error,
            },
        )

        try:
            if usage.input_tokens:
                self.cfg.emit_usage(
                    org_id=actor.org_id,
                    unit="tokens_in",
                    qty=usage.input_tokens,
                    module="gateway",
                    model=model_used,
                    actor_kind=actor.kind,
                    actor_user_id=actor.user_id,
                )
            if usage.output_tokens:
                self.cfg.emit_usage(
                    org_id=actor.org_id,
                    unit="tokens_out",
                    qty=usage.output_tokens,
                    module="gateway",
                    model=model_used,
                    actor_kind=actor.kind,
                    actor_user_id=actor.user_id,
                )
            if usage.cache_read_tokens:
                self.cfg.emit_usage(
                    org_id=actor.org_id,
                    unit="tokens_cache_read",
                    qty=usage.cache_read_tokens,
                    module="gateway",
                    model=model_used,
                    actor_kind=actor.kind,
                    actor_user_id=actor.user_id,
                )
            if usage.cache_write_tokens:
                self.cfg.emit_usage(
                    org_id=actor.org_id,
                    unit="tokens_cache_write",
                    qty=usage.cache_write_tokens,
                    module="gateway",
                    model=model_used,
                    actor_kind=actor.kind,
                    actor_user_id=actor.user_id,
                )
        except Exception:  # noqa: BLE001
            logger.exception("facade._record: emit_usage failed")

    def _safe_audit(
        self, *, event_type: str, actor: Actor, payload: dict[str, Any]
    ) -> None:
        try:
            self.cfg.emit_audit(
                event_type=event_type,
                org_id=actor.org_id,
                actor=actor.to_dict(),
                actor_user_id=actor.user_id,
                actor_type=actor.kind,
                payload=payload,
                action=event_type.split(".", 1)[-1],
            )
        except Exception:  # noqa: BLE001
            logger.exception("facade._safe_audit: emit_audit failed")


# ── module-level default facade ──────────────────────────────────────────


_DEFAULT_FACADE: GatewayFacade | None = None


def set_default_facade(
    facade: GatewayFacade | None,
) -> GatewayFacade | None:
    """Install a process-wide default facade. Returns the previous value.

    Production startup calls this once with a fully-wired facade; tests use
    the returned token to restore the previous value in a ``finally`` block.
    """
    global _DEFAULT_FACADE
    prev = _DEFAULT_FACADE
    _DEFAULT_FACADE = facade
    return prev


def get_default_facade() -> GatewayFacade:
    """Return the installed default facade or raise if unset."""
    if _DEFAULT_FACADE is None:
        raise RuntimeError(
            "no default GatewayFacade installed — call set_default_facade() "
            "from app startup or pass a facade explicitly."
        )
    return _DEFAULT_FACADE


# ── module-level shortcuts (re-exported by gateway/__init__.py) ──────────


async def complete(req: LLMRequest, actor: Actor) -> LLMResponse:
    return await get_default_facade().complete(req, actor)


async def stream(req: LLMRequest, actor: Actor) -> AsyncIterator[StreamChunk]:
    async for chunk in get_default_facade().stream(req, actor):
        yield chunk


async def embed(texts: list[str], *, model: str, actor: Actor) -> Embeddings:
    return await get_default_facade().embed(texts, model=model, actor=actor)


async def rerank(
    *,
    query: str,
    documents: list[str],
    model: str,
    actor: Actor,
    top_k: int | None = None,
    return_documents: bool = False,
) -> list[Any]:
    return await get_default_facade().rerank(
        query=query,
        documents=documents,
        model=model,
        actor=actor,
        top_k=top_k,
        return_documents=return_documents,
    )


def count_tokens(text: str, *, model: str) -> int:
    return get_default_facade().count_tokens(text, model=model)


def estimate_cost(req: LLMRequest, *, model: str) -> float:
    return get_default_facade().estimate_cost(req, model=model)


__all__ = [
    "Actor",
    "FacadeConfig",
    "GatewayFacade",
    "complete",
    "count_tokens",
    "embed",
    "estimate_cost",
    "get_default_facade",
    "rerank",
    "set_default_facade",
    "stream",
]
