"""Routing service — alias → policy → strategy → candidate.

The pure-Python wiring used by both internal callers (chat module, RAG)
and HTTP-compat surfaces (OpenAI, Anthropic, Bedrock). Provider
invocation lives on top of this — :meth:`resolve` only returns *which*
candidate to use plus the routing decision metadata.

Resolution flow:

1. If the request's ``model`` matches a concrete candidate by either
   ``model_id`` or ``provider:model_id`` form, return it directly. This is
   the fast path — no DB hit, no policy lookup. Lets clients keep using
   raw model ids (``"claude-sonnet-4-6"``).

2. Otherwise look up a :class:`ModelAlias` for the request's org +
   ``req.model``. If found, load the associated :class:`RoutingPolicy`.

3. If a ``policy_override`` was supplied (typically from the
   ``x-gateway-routing-policy`` request header), it takes precedence over
   the alias's default policy. Override is by policy *name*.

4. Run ``policy.strategy.pick(req, candidates, ctx)`` and return the
   resolution.

5. If none of the above matched, raise :class:`RoutingError`.

The service is intentionally stateless — :meth:`resolve` is the only
public entry. A request-id-bound trace logger should call this in the
hot path and record ``RoutingResolution`` into the trace row.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.gateway.routing.model import ModelAlias, RoutingPolicy
from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
)
from ai_portal.gateway.routing.registry import get_strategy
from ai_portal.gateway.types import LLMRequest

# Header name clients use to override the default policy.
ROUTING_POLICY_HEADER = "x-gateway-routing-policy"


@dataclass(frozen=True)
class RoutingResolution:
    """The decision the router made for one request.

    Persisted in ``request_traces.routing_decision`` so admins can replay /
    audit how a call ended up on a given model.
    """

    candidate: ProviderModel
    policy_id: _uuid.UUID | None
    policy_name: str | None
    strategy: str | None
    alias: str | None


class RoutingService:
    """Resolves the request's ``model`` to one concrete candidate."""

    def __init__(self, db: Session | None) -> None:
        self.db = db

    # ── public ───────────────────────────────────────────────────────────

    def resolve(
        self,
        *,
        req: LLMRequest,
        org_id: _uuid.UUID,
        candidates: list[ProviderModel],
        policy_override: str | None = None,
        metrics: dict[tuple[str, str], float] | None = None,
    ) -> RoutingResolution:
        """Resolve ``req.model`` → :class:`RoutingResolution`.

        ``policy_override`` is the policy *name* (per-org) — typically
        sourced from the ``x-gateway-routing-policy`` request header.

        ``metrics`` (optional) carries fresh observed latencies passed
        through to latency-aware strategies.
        """
        if not candidates:
            raise RoutingError("no candidates supplied")

        # 1. Header override wins, regardless of alias.
        if policy_override:
            return self._resolve_via_policy_name(
                req=req,
                org_id=org_id,
                policy_name=policy_override,
                candidates=candidates,
                alias=None,
                metrics=metrics,
            )

        # 2. Concrete model match — fast path, no DB.
        concrete = self._concrete_match(req.model, candidates)
        if concrete is not None:
            return RoutingResolution(
                candidate=concrete,
                policy_id=None,
                policy_name=None,
                strategy=None,
                alias=None,
            )

        # 3. Alias lookup.
        if self.db is not None:
            alias = self._lookup_alias(org_id=org_id, name=req.model)
            if alias is not None:
                policy = self.db.get(RoutingPolicy, alias.routing_policy_id)
                if policy is None or policy.org_id != org_id:
                    raise RoutingError(
                        f"alias {req.model!r} points to missing policy"
                    )
                return self._run_strategy(
                    req=req,
                    policy=policy,
                    candidates=candidates,
                    alias=alias.alias,
                    metrics=metrics,
                )

        # 4. Nothing matched.
        raise RoutingError(
            f"no concrete match, alias, or policy override for model {req.model!r}"
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _concrete_match(
        self, model: str, candidates: list[ProviderModel]
    ) -> ProviderModel | None:
        """Match by ``model_id`` or ``provider:model_id``."""
        if ":" in model:
            provider, _, model_id = model.partition(":")
            for c in candidates:
                if c.provider == provider and c.model_id == model_id:
                    return c
            return None
        for c in candidates:
            if c.model_id == model:
                return c
        return None

    def _lookup_alias(self, *, org_id: _uuid.UUID, name: str) -> ModelAlias | None:
        assert self.db is not None
        return self.db.scalar(
            select(ModelAlias).where(
                ModelAlias.org_id == org_id,
                ModelAlias.alias == name,
            )
        )

    def _resolve_via_policy_name(
        self,
        *,
        req: LLMRequest,
        org_id: _uuid.UUID,
        policy_name: str,
        candidates: list[ProviderModel],
        alias: str | None,
        metrics: dict[tuple[str, str], float] | None,
    ) -> RoutingResolution:
        if self.db is None:
            raise RoutingError(
                "routing policy override requires a DB session"
            )
        policy = self.db.scalar(
            select(RoutingPolicy).where(
                RoutingPolicy.org_id == org_id,
                RoutingPolicy.name == policy_name,
            )
        )
        if policy is None:
            raise RoutingError(
                f"routing policy {policy_name!r} not found for org"
            )
        return self._run_strategy(
            req=req,
            policy=policy,
            candidates=candidates,
            alias=alias,
            metrics=metrics,
        )

    def _run_strategy(
        self,
        *,
        req: LLMRequest,
        policy: RoutingPolicy,
        candidates: list[ProviderModel],
        alias: str | None,
        metrics: dict[tuple[str, str], float] | None,
    ) -> RoutingResolution:
        try:
            strategy = get_strategy(policy.strategy)
        except KeyError as exc:
            raise RoutingError(str(exc)) from exc
        ctx = RoutingCtx(
            rules=dict(policy.rules_json or {}),
            metrics=metrics or {},
        )
        pick = strategy.pick(req, candidates, ctx)
        return RoutingResolution(
            candidate=pick,
            policy_id=policy.id,
            policy_name=policy.name,
            strategy=policy.strategy,
            alias=alias,
        )


def extract_policy_override(headers: dict[str, str] | None) -> str | None:
    """Return the policy-override name from request headers, or ``None``.

    Header lookup is case-insensitive — ``x-gateway-routing-policy`` and
    ``X-Gateway-Routing-Policy`` are equivalent. Helper exists so callers
    (FastAPI deps, internal facade) don't duplicate the casing rules.
    """
    if not headers:
        return None
    for k, v in headers.items():
        if k.lower() == ROUTING_POLICY_HEADER:
            v = (v or "").strip()
            return v or None
    return None


__all__ = [
    "ROUTING_POLICY_HEADER",
    "RoutingResolution",
    "RoutingService",
    "extract_policy_override",
]
