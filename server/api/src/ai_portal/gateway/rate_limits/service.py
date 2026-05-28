"""Service layer for gateway rate limits.

Three responsibilities:

1. **Rule CRUD** — :meth:`RateLimitService.create`, :meth:`list_for_org`,
   :meth:`delete`. The rule shape mirrors :class:`RateLimitRule`.
2. **Rule matching** — :meth:`effective_rules_for(actor, model)` returns the
   subset of an org's rules that apply to the (actor, model) tuple. Scope
   matching is conjunctive: every key in ``scope_json`` must equal the
   value supplied at check time. An empty ``scope_json`` matches everything
   ("org default").
3. **Enforcement** — :meth:`check(actor, model, tokens, dimension)`. Looks up
   rules in the bucket backend, consumes the requested token count, and
   raises :class:`RateLimitExceeded` (carrying ``retry_after``) on denial.

The matching service also feeds :func:`limits_for_actor` which powers the
``GET /v1/limits/me`` route — it returns one :class:`LimitView` per matched
rule with the current remaining quota.
"""

from __future__ import annotations

import math
import time
import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.gateway.rate_limits.bucket import (
    ConsumeResult,
    InMemoryBucket,
    TokenBucket,
)
from ai_portal.gateway.rate_limits.model import RateLimitRule

Dimension = Literal["rpm", "tpm", "concurrent_requests"]


class RateLimitExceeded(Exception):
    """Raised when the bucket denies a consume call.

    Carries ``retry_after`` (seconds) so the route handler can surface a
    ``Retry-After`` header.
    """

    def __init__(
        self,
        *,
        dimension: Dimension,
        limit: int,
        retry_after: int,
        scope: dict,
    ) -> None:
        self.dimension = dimension
        self.limit = limit
        self.retry_after = max(1, retry_after)
        self.scope = scope
        super().__init__(
            f"rate limit exceeded: {dimension} (limit={limit}, retry_after={self.retry_after}s)"
        )


@dataclass(frozen=True)
class LimitView:
    """One row in the ``GET /v1/limits/me`` response."""

    rule_id: _uuid.UUID
    dimension: Dimension
    period_seconds: int
    limit_value: int
    burst: int
    remaining: int
    scope: dict


def _scope_matches(rule_scope: dict, actor_scope: dict) -> bool:
    """Conjunctive match. Missing keys in ``rule_scope`` match anything."""
    for k, v in rule_scope.items():
        if actor_scope.get(k) != v:
            return False
    return True


def _bucket_key(*, org_id: _uuid.UUID, rule_id: _uuid.UUID, actor_scope: dict) -> str:
    """Stable key combining the rule + the concrete actor it's being checked
    against. Two users matching the same org-default rule each get their own
    bucket so one user can't drain another's quota.
    """
    parts = [f"gw:rl:{org_id}:{rule_id}"]
    for k in ("actor_user_id", "api_key_id", "team_id", "model"):
        if k in actor_scope:
            parts.append(f"{k}={actor_scope[k]}")
    return "|".join(parts)


class RateLimitService:
    """Persistence + enforcement orchestrator."""

    def __init__(self, db: Session, *, bucket: TokenBucket | None = None) -> None:
        self.db = db
        self.bucket: TokenBucket = bucket or InMemoryBucket()

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        org_id: _uuid.UUID,
        dimension: Dimension,
        limit_value: int,
        period_seconds: int = 60,
        burst: int = 0,
        scope: dict | None = None,
    ) -> RateLimitRule:
        rule = RateLimitRule(
            org_id=org_id,
            dimension=dimension,
            period_seconds=period_seconds,
            limit_value=limit_value,
            burst=burst,
            scope_json=dict(scope or {}),
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def list_for_org(self, org_id: _uuid.UUID) -> Sequence[RateLimitRule]:
        return list(
            self.db.scalars(
                select(RateLimitRule)
                .where(RateLimitRule.org_id == org_id)
                .order_by(RateLimitRule.created_at.desc())
            )
        )

    def delete(self, *, org_id: _uuid.UUID, rule_id: _uuid.UUID) -> bool:
        rule = self.db.get(RateLimitRule, rule_id)
        if rule is None or rule.org_id != org_id:
            return False
        self.db.delete(rule)
        self.db.commit()
        return True

    # ── matching ─────────────────────────────────────────────────────────

    def effective_rules(
        self,
        *,
        org_id: _uuid.UUID,
        actor_scope: dict,
        dimension: Dimension | None = None,
    ) -> list[RateLimitRule]:
        """Return rules whose scope matches ``actor_scope`` for ``dimension``."""
        q = select(RateLimitRule).where(RateLimitRule.org_id == org_id)
        if dimension is not None:
            q = q.where(RateLimitRule.dimension == dimension)
        out: list[RateLimitRule] = []
        for rule in self.db.scalars(q):
            if _scope_matches(rule.scope_json or {}, actor_scope):
                out.append(rule)
        return out

    # ── enforcement ──────────────────────────────────────────────────────

    def check(
        self,
        *,
        org_id: _uuid.UUID,
        actor_scope: dict,
        dimension: Dimension,
        tokens: int = 1,
    ) -> list[ConsumeResult]:
        """Consume ``tokens`` against every matching rule.

        Raises :class:`RateLimitExceeded` on the first rule that denies. All
        rules that *passed* before the denying one have already consumed —
        this matches token-bucket semantics where slightly-over-budget
        callers get a fast denial without rollback.
        """
        rules = self.effective_rules(
            org_id=org_id, actor_scope=actor_scope, dimension=dimension
        )
        results: list[ConsumeResult] = []
        for rule in rules:
            capacity = float(rule.limit_value + max(0, rule.burst))
            if dimension == "concurrent_requests":
                refill_rate = 0.0
            else:
                refill_rate = (
                    float(rule.limit_value) / float(rule.period_seconds)
                    if rule.period_seconds > 0
                    else float(rule.limit_value)
                )
            key = _bucket_key(org_id=org_id, rule_id=rule.id, actor_scope=actor_scope)
            res = self.bucket.consume(
                key,
                capacity=capacity,
                refill_per_second=refill_rate,
                tokens=float(tokens),
            )
            results.append(res)
            if not res.allowed:
                raise RateLimitExceeded(
                    dimension=dimension,
                    limit=rule.limit_value,
                    retry_after=res.retry_after,
                    scope=dict(rule.scope_json or {}),
                )
        return results

    def release_concurrent(
        self,
        *,
        org_id: _uuid.UUID,
        actor_scope: dict,
        tokens: int = 1,
    ) -> None:
        """Return tokens to every matching ``concurrent_requests`` bucket."""
        rules = self.effective_rules(
            org_id=org_id,
            actor_scope=actor_scope,
            dimension="concurrent_requests",
        )
        for rule in rules:
            key = _bucket_key(org_id=org_id, rule_id=rule.id, actor_scope=actor_scope)
            self.bucket.release(key, tokens=float(tokens))

    # ── introspection (powers /v1/limits/me) ─────────────────────────────

    def limits_for_actor(
        self,
        *,
        org_id: _uuid.UUID,
        actor_scope: dict,
    ) -> list[LimitView]:
        """Effective rules + current remaining quota."""
        rules = self.effective_rules(org_id=org_id, actor_scope=actor_scope)
        views: list[LimitView] = []
        for rule in rules:
            capacity = float(rule.limit_value + max(0, rule.burst))
            if rule.dimension == "concurrent_requests":
                refill_rate = 0.0
            else:
                refill_rate = (
                    float(rule.limit_value) / float(rule.period_seconds)
                    if rule.period_seconds > 0
                    else float(rule.limit_value)
                )
            key = _bucket_key(org_id=org_id, rule_id=rule.id, actor_scope=actor_scope)
            level = self.bucket.peek(
                key, capacity=capacity, refill_per_second=refill_rate
            )
            views.append(
                LimitView(
                    rule_id=rule.id,
                    dimension=rule.dimension,  # type: ignore[arg-type]
                    period_seconds=rule.period_seconds,
                    limit_value=rule.limit_value,
                    burst=rule.burst,
                    remaining=int(math.floor(max(0.0, level))),
                    scope=dict(rule.scope_json or {}),
                )
            )
        return views


# ── FastAPI helper ──────────────────────────────────────────────────────────


def check_rate_limit(
    db: Session,
    *,
    org_id: _uuid.UUID,
    actor_scope: dict,
    dimension: Dimension,
    tokens: int = 1,
    bucket: TokenBucket | None = None,
) -> None:
    """Convenience wrapper used by FastAPI deps + middleware.

    Raises :class:`RateLimitExceeded`; the caller is expected to translate
    that into ``HTTPException(429, headers={"Retry-After": ...})``.
    """
    svc = RateLimitService(db, bucket=bucket) if bucket else RateLimitService(db)
    svc.check(
        org_id=org_id,
        actor_scope=actor_scope,
        dimension=dimension,
        tokens=tokens,
    )


# silence "imported-but-unused" for time when consumers re-import (e.g. tests).
_ = time
