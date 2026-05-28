"""GET /v1/models — unified, OpenAI-shaped listing.

Returns every concrete model in ``gateway_models`` whose ``provider`` the
calling org has credentials for. Deprecated rows (``deprecated_at`` set in
the past) are filtered out. Optional ``?provider=`` query narrows further.

Response shape mirrors OpenAI's ``GET /v1/models``::

    {
      "object": "list",
      "data": [
        {"id": "claude-sonnet-4-6", "object": "model",
         "created": 1700000000, "owned_by": "anthropic",
         "capabilities": ["chat", "streaming", ...]}
      ]
    }

CRUD on credentials / the catalog itself lives in Phase J — this surface is
strictly read-only and SDK-compatible.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.catalog.model import GatewayModel
from ai_portal.control_plane.deps import require_actor
from ai_portal.gateway.provider_credentials.model import ProviderCredential
from ai_portal.rbac.service import Actor

router = APIRouter(tags=["gateway-models"])


# ── schemas ──────────────────────────────────────────────────────────────


class ModelOut(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str
    display_name: str
    capabilities: list[str]
    price_input_per_1k_cents: int
    price_output_per_1k_cents: int
    price_cache_read_per_1k_cents: int


class ModelsListResponse(BaseModel):
    object: str = "list"
    data: list[ModelOut]


# ── helpers ──────────────────────────────────────────────────────────────


def _enabled_providers_for_org(db: Session, org_id) -> set[str]:
    """Return the set of provider names the org has at least one credential for."""
    rows = db.scalars(
        select(ProviderCredential.provider).where(ProviderCredential.org_id == org_id)
    ).all()
    return {r for r in rows}


def _to_out(m: GatewayModel) -> ModelOut:
    return ModelOut(
        id=m.model_id,
        created=int(m.created_at.timestamp()) if m.created_at else 0,
        owned_by=m.provider,
        display_name=m.display_name,
        capabilities=list(m.capabilities_json or []),
        price_input_per_1k_cents=m.price_input_per_1k_cents,
        price_output_per_1k_cents=m.price_output_per_1k_cents,
        price_cache_read_per_1k_cents=m.price_cache_read_per_1k_cents,
    )


# ── route ────────────────────────────────────────────────────────────────


@router.get("/v1/models", response_model=ModelsListResponse)
def list_models(
    provider: str | None = Query(default=None, description="Filter by provider name"),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
) -> ModelsListResponse:
    """List every concrete model the calling org can reach."""
    enabled = _enabled_providers_for_org(db, actor.org_id)
    if not enabled:
        return ModelsListResponse(data=[])

    if provider is not None:
        if provider not in enabled:
            return ModelsListResponse(data=[])
        enabled = {provider}

    now = datetime.now(UTC)
    stmt = (
        select(GatewayModel)
        .where(GatewayModel.provider.in_(enabled))
        .order_by(GatewayModel.provider, GatewayModel.model_id)
    )
    rows = list(db.scalars(stmt).all())
    rows = [
        r
        for r in rows
        if r.deprecated_at is None or r.deprecated_at > now
    ]
    return ModelsListResponse(data=[_to_out(r) for r in rows])


__all__ = ["router", "ModelsListResponse", "ModelOut"]
