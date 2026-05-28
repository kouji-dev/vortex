"""Gateway policy orchestration — cache → budget → dispatch → cost → trace.

Wraps the raw :func:`gateway.service.complete` call with cross-cutting policy
glue:

- pre-call **budget** check (G2) — short-circuits with a ``block`` decision
  and 402-shaped headers when ``incoming_cost_usd`` would breach the cap
- pre-call **cache** lookup (E2) — returns cached response, marks
  ``cache_hit=True``, emits a usage event with ``tokens_cache_read``
- **dispatch** to the provider
- post-call **cost** computation (G1) — exposed via ``x-gateway-cost-cents``
  header and surfaced for trace persistence

This function is provider- and FastAPI-agnostic so it can be reused by every
compat layer (OpenAI, Anthropic, Bedrock) and by internal callers (chat,
RAG, memories). Callers are responsible for actually attaching the returned
headers to the HTTP response and writing the returned record to the trace
table.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from ai_portal.gateway import service as gateway_service
from ai_portal.gateway.cache.protocol import Cache
from ai_portal.gateway.pricing import PricingSnapshot, compute_cost_cents
from ai_portal.gateway.types import LLMRequest, LLMResponse  # noqa: F401

# ── budget check protocol (decoupled from sqlalchemy) ───────────────────────


class BudgetChecker(Protocol):
    """Pre-call budget check callable.

    Returning a decision with ``is_blocked=True`` aborts the call. Truthy
    ``reason`` populates the ``x-gateway-budget-status`` header. The shape
    matches :class:`ai_portal.budgets.service.BudgetDecision`.
    """

    def __call__(self, *, incoming_cost_usd: float) -> _BudgetDecisionLike: ...


class _BudgetDecisionLike(Protocol):
    is_blocked: bool
    reason: str


# ── exceptions ──────────────────────────────────────────────────────────────


class BudgetExceeded(Exception):
    """Raised by :func:`complete_with_policies` on a hard-cutoff budget block.

    The compat layer translates this into a 402 Payment Required response
    with the ``x-gateway-budget-status`` header set.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.headers: dict[str, str] = {
            "x-gateway-budget-status": "blocked",
            "x-gateway-budget-reason": reason,
        }


# ── result ──────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class PolicyResult:
    """Output of :func:`complete_with_policies`.

    - ``response`` — the LLMResponse, either freshly produced or from cache
    - ``cost_cents`` — computed cost in cents (cache hits = 0)
    - ``cache_hit`` — True when response came from the cache
    - ``headers`` — headers to attach to the outgoing HTTP response
    - ``trace_extra`` — extra fields the caller should merge into its trace row
    """

    response: LLMResponse
    cost_cents: float = 0.0
    cache_hit: bool = False
    headers: dict[str, str] = field(default_factory=dict)
    trace_extra: dict[str, Any] = field(default_factory=dict)


# ── cache key ───────────────────────────────────────────────────────────────


def compute_request_hash(req: LLMRequest) -> str:
    """Stable SHA-256 hash over the canonical request.

    Skips fields that should not invalidate the cache (``stream``, ``user``).
    """
    body = req.model_dump(mode="json", exclude={"stream", "user"})
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ── policy-aware complete ──────────────────────────────────────────────────


async def complete_with_policies(
    req: LLMRequest,
    provider: Any,
    *,
    pricing: PricingSnapshot | None = None,
    cache: Cache | None = None,
    cache_ttl_seconds: int = 300,
    budget_check: BudgetChecker | None = None,
    estimated_cost_usd: float = 0.0,
    on_cache_hit_usage: UsageEmitter | None = None,  # noqa: F821
) -> PolicyResult:
    """Run a completion with cache + budget + cost policy glue applied.

    Order:
    1. Budget check (pre-call) — raises :class:`BudgetExceeded` on block.
    2. Cache lookup — returns cached on hit, emits usage event for cache_read.
    3. Dispatch to provider.
    4. Cost calc + cache store + result construction.
    """

    headers: dict[str, str] = {}

    # ── 1. Budget check ────────────────────────────────────────────────────
    if budget_check is not None:
        decision = budget_check(incoming_cost_usd=estimated_cost_usd)
        if getattr(decision, "is_blocked", False):
            raise BudgetExceeded(getattr(decision, "reason", "budget exceeded"))
        headers["x-gateway-budget-status"] = decision_action(decision)

    # ── 2. Cache lookup ────────────────────────────────────────────────────
    request_hash: str | None = None
    if cache is not None:
        request_hash = compute_request_hash(req)
        cached_blob = await cache.get(request_hash)
        if cached_blob is not None:
            try:
                cached_resp = LLMResponse.model_validate(cached_blob)
            except Exception:  # noqa: BLE001
                cached_resp = None
            if cached_resp is not None:
                headers["x-gateway-cache-hit"] = "true"
                headers["x-gateway-cost-cents"] = "0.000000"
                if on_cache_hit_usage is not None:
                    on_cache_hit_usage(
                        tokens_cache_read=cached_resp.usage.input_tokens,
                        model=cached_resp.model_used,
                    )
                return PolicyResult(
                    response=cached_resp,
                    cost_cents=0.0,
                    cache_hit=True,
                    headers=headers,
                    trace_extra={
                        "cache_hit": True,
                        "request_hash": request_hash,
                        "tokens_cache_read": cached_resp.usage.input_tokens,
                        "tokens_in": 0,
                        "tokens_out": 0,
                    },
                )

    # ── 3. Dispatch ────────────────────────────────────────────────────────
    resp = await gateway_service.complete(req, provider)

    # ── 4. Cost + cache write ──────────────────────────────────────────────
    cost = 0.0
    if pricing is not None:
        cost = compute_cost_cents(resp.usage, pricing)
    headers["x-gateway-cost-cents"] = f"{cost:.6f}"
    headers["x-gateway-cache-hit"] = "false"

    if cache is not None and request_hash is not None:
        # Store as JSON-safe dict so any backend can persist it.
        try:
            await cache.set(
                request_hash,
                resp.model_dump(mode="json"),
                ttl=cache_ttl_seconds,
            )
        except Exception:  # noqa: BLE001 — never fail the call on cache write
            pass

    return PolicyResult(
        response=resp,
        cost_cents=cost,
        cache_hit=False,
        headers=headers,
        trace_extra={
            "cache_hit": False,
            "request_hash": request_hash,
            "tokens_in": resp.usage.input_tokens,
            "tokens_out": resp.usage.output_tokens,
            "tokens_cache_read": resp.usage.cache_read_tokens,
            "tokens_cache_write": resp.usage.cache_write_tokens,
            "cost_cents": cost,
        },
    )


def decision_action(decision: _BudgetDecisionLike) -> str:
    """Map a BudgetDecision-like value into a header-safe string."""
    return getattr(decision, "action", "allow")


# ── on-cache-hit usage hook protocol ────────────────────────────────────────


class UsageEmitter(Protocol):
    """Callback used to emit a ``tokens_cache_read`` usage event on a cache hit.

    Decoupled from the DB session so callers can wire either ``emit_usage``
    or a stub for tests.
    """

    def __call__(self, *, tokens_cache_read: int, model: str) -> None: ...


__all__ = [
    "BudgetChecker",
    "BudgetExceeded",
    "PolicyResult",
    "UsageEmitter",
    "complete_with_policies",
    "compute_request_hash",
]
