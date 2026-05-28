"""Gateway admin list endpoints — minimal GETs to populate UI dropdowns.

Surfaces three resources at `/v1/gateway/...`:
- `provider_credentials` — per-org provider creds (no secrets in responses)
- `routing_policies` — per-org routing policies
- `model_aliases` — per-org model alias mappings
- `models` — global catalog of gateway models

CRUD is intentionally minimal here; the heavy lifting lives in each module's
service layer. These endpoints unblock the frontend Gateway admin pages.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.catalog.model import GatewayModel
from ai_portal.gateway.provider_credentials.model import ProviderCredential
from ai_portal.gateway.routing.model import ModelAlias, RoutingPolicy

router = APIRouter(prefix="/v1/gateway", tags=["gateway-admin"])


@router.get("/providers/credentials")
def list_provider_credentials(
    _request: Request,
    user: User = Depends(get_current_user),
    org_id=Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(ProviderCredential).where(ProviderCredential.org_id == str(org_id))
    ).all()
    return [
        {
            "id": str(r.id),
            "provider": r.provider,
            "label": r.label,
            "healthy": bool(r.healthy),
            "last_health_at": r.last_health_at.isoformat() if r.last_health_at else None,
        }
        for r in rows
    ]


@router.get("/models")
def list_gateway_models(
    _request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(GatewayModel).where(GatewayModel.deprecated_at.is_(None))
    ).all()
    return [
        {
            "id": str(r.id),
            "provider": r.provider,
            "model_id": r.model_id,
            "display_name": r.display_name,
            "capabilities": r.capabilities_json or {},
            "price_input_per_1k_cents": float(r.price_input_per_1k_cents or 0),
            "price_output_per_1k_cents": float(r.price_output_per_1k_cents or 0),
        }
        for r in rows
    ]


@router.get("/routing-policies")
def list_routing_policies(
    _request: Request,
    user: User = Depends(get_current_user),
    org_id=Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(RoutingPolicy).where(RoutingPolicy.org_id == str(org_id))
    ).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "strategy": r.strategy,
            "rules": r.rules_json or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/model-aliases")
def list_model_aliases(
    _request: Request,
    user: User = Depends(get_current_user),
    org_id=Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(ModelAlias).where(ModelAlias.org_id == str(org_id))
    ).all()
    return [
        {
            "id": str(r.id),
            "alias": r.alias,
            "routing_policy_id": str(r.routing_policy_id) if r.routing_policy_id else None,
        }
        for r in rows
    ]
