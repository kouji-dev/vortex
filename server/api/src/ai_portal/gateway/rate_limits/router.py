"""Gateway rate-limit HTTP surface.

Routes:

- ``GET /v1/limits/me`` — introspect the caller's effective limits +
  remaining quota. Powers the dashboard "your usage" pane and the CLI
  ``ai-portal limits`` command.

CRUD routes for ``rate_limit_rules`` are out of scope for Phase D — they
land with the rest of the gateway admin surface in Phase J.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_actor
from ai_portal.gateway.rate_limits.service import (
    LimitView,
    RateLimitService,
)
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1/limits", tags=["gateway-rate-limits"])


# ── Schemas ──────────────────────────────────────────────────────────────


class LimitOut(BaseModel):
    rule_id: str
    dimension: str
    period_seconds: int
    limit: int
    burst: int
    remaining: int
    scope: dict


class LimitsMeResponse(BaseModel):
    actor: dict
    limits: list[LimitOut]


def _actor_scope(actor: Actor) -> dict:
    """Build the scope dict used for rule matching."""
    scope: dict = {}
    if actor.user_id is not None:
        scope["actor_user_id"] = actor.user_id
    if actor.api_key_id is not None:
        scope["api_key_id"] = actor.api_key_id
    return scope


def _to_out(v: LimitView) -> LimitOut:
    return LimitOut(
        rule_id=str(v.rule_id),
        dimension=v.dimension,
        period_seconds=v.period_seconds,
        limit=v.limit_value,
        burst=v.burst,
        remaining=v.remaining,
        scope=dict(v.scope),
    )


# ── Routes ───────────────────────────────────────────────────────────────


@router.get("/me", response_model=LimitsMeResponse)
def get_my_limits(
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
) -> LimitsMeResponse:
    """Return effective rate limits + remaining quota for the caller."""
    svc = RateLimitService(db)
    scope = _actor_scope(actor)
    views = svc.limits_for_actor(org_id=actor.org_id, actor_scope=scope)
    return LimitsMeResponse(
        actor={
            "kind": actor.kind,
            "user_id": actor.user_id,
            "api_key_id": actor.api_key_id,
            "org_id": str(actor.org_id),
        },
        limits=[_to_out(v) for v in views],
    )
