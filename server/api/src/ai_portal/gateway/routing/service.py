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
from datetime import UTC, datetime

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
    # When the request used ``model@DATE`` pinning syntax, the parsed
    # datetime. ``None`` for unpinned requests.
    pin_date: datetime | None = None


# ── model pinning helpers ─────────────────────────────────────────────────


def parse_pinned_model(model: str) -> tuple[str, datetime | None]:
    """Split ``"alias@DATE"`` into ``(alias, pin_date)``.

    Returns ``(model, None)`` when no ``@`` is present. Raises
    :class:`ValueError` when the date suffix is malformed so callers can
    surface a 400.

    The date is parsed with :func:`datetime.fromisoformat`; bare dates
    (``2026-05-01``) are accepted and normalised to UTC midnight.
    """
    if "@" not in model:
        return model, None
    base, _, suffix = model.partition("@")
    if not suffix:
        raise ValueError(f"empty pin date in {model!r}")
    try:
        dt = datetime.fromisoformat(suffix)
    except ValueError as exc:
        raise ValueError(f"invalid pin date in {model!r}: {suffix}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return base, dt


def filter_candidates_by_pin_date(
    candidates: list[ProviderModel], pin_date: datetime | None
) -> list[ProviderModel]:
    """Keep candidates active at ``pin_date``.

    A model is considered active when ``deprecated_at`` is ``None`` or
    strictly after ``pin_date``. ``pin_date=None`` returns the input
    unchanged.
    """
    if pin_date is None:
        return list(candidates)
    return [
        c
        for c in candidates
        if c.deprecated_at is None or c.deprecated_at > pin_date
    ]


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

        # 0. Strip pin-date suffix if present (``"smart@2026-05-01"``).
        base_model, pin_date = parse_pinned_model(req.model)
        if pin_date is not None:
            candidates = filter_candidates_by_pin_date(candidates, pin_date)
            if not candidates:
                raise RoutingError(
                    f"no candidates active at pin date {pin_date.isoformat()}"
                )

        # 1. Header override wins, regardless of alias.
        if policy_override:
            res = self._resolve_via_policy_name(
                req=req,
                org_id=org_id,
                policy_name=policy_override,
                candidates=candidates,
                alias=None,
                metrics=metrics,
            )
            return _with_pin(res, pin_date)

        # 2. Concrete model match — fast path, no DB.
        concrete = self._concrete_match(base_model, candidates)
        if concrete is not None:
            return RoutingResolution(
                candidate=concrete,
                policy_id=None,
                policy_name=None,
                strategy=None,
                alias=None,
                pin_date=pin_date,
            )

        # 3. Alias lookup.
        if self.db is not None:
            alias = self._lookup_alias(org_id=org_id, name=base_model)
            if alias is not None:
                policy = self.db.get(RoutingPolicy, alias.routing_policy_id)
                if policy is None or policy.org_id != org_id:
                    raise RoutingError(
                        f"alias {base_model!r} points to missing policy"
                    )
                res = self._run_strategy(
                    req=req,
                    policy=policy,
                    candidates=candidates,
                    alias=alias.alias,
                    metrics=metrics,
                )
                return _with_pin(res, pin_date)

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
            raise RoutingError("routing policy override requires a DB session")
        policy = self.db.scalar(
            select(RoutingPolicy).where(
                RoutingPolicy.org_id == org_id,
                RoutingPolicy.name == policy_name,
            )
        )
        if policy is None:
            raise RoutingError(f"routing policy {policy_name!r} not found for org")
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


def _with_pin(res: RoutingResolution, pin_date: datetime | None) -> RoutingResolution:
    """Attach a ``pin_date`` to an existing :class:`RoutingResolution`."""
    if pin_date is None:
        return res
    return RoutingResolution(
        candidate=res.candidate,
        policy_id=res.policy_id,
        policy_name=res.policy_name,
        strategy=res.strategy,
        alias=res.alias,
        pin_date=pin_date,
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
    "filter_candidates_by_pin_date",
    "parse_pinned_model",
]
