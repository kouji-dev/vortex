"""Billing API — /v1/billing/*.

Endpoints:
- GET    /v1/billing/subscription   — current org subscription (admin/owner)
- PATCH  /v1/billing/subscription   — change plan / seats / cancel
- GET    /v1/billing/invoices       — list invoices for org
- POST   /v1/billing/webhook        — Stripe webhook receiver (unauth, signed)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.billing.deps import get_billing_provider
from ai_portal.billing.protocol import (
    BillingProvider,
    BillingProviderError,
)
from ai_portal.billing.providers.stripe import StripeBillingProvider
from ai_portal.billing.schemas import (
    InvoiceList,
    InvoiceOut,
    SubscriptionOut,
    SubscriptionPatch,
)
from ai_portal.billing.service import (
    BillingService,
    NoSubscriptionForOrg,
    UnknownPlan,
    get_plan,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/billing", tags=["billing"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, "owner", "admin")
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org context")
    return user


def _to_sub_out(row) -> SubscriptionOut:
    return SubscriptionOut.model_validate(row)


def _to_inv_out(row) -> InvoiceOut:
    return InvoiceOut.model_validate(row)


# ── Subscription ────────────────────────────────────────────────────────────


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
) -> SubscriptionOut:
    svc = BillingService(db, provider)
    row = svc.get_subscription(org_id=user.org_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No subscription for org",
        )
    return _to_sub_out(row)


@router.patch("/subscription", response_model=SubscriptionOut)
async def patch_subscription(
    body: SubscriptionPatch,
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
) -> SubscriptionOut:
    svc = BillingService(db, provider)

    if body.cancel:
        try:
            row = await svc.cancel(org_id=user.org_id)
        except NoSubscriptionForOrg as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
        db.commit()
        return _to_sub_out(row)

    if not body.plan_code and body.seats is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="plan_code or seats required",
        )

    # Existing subscription drives defaults when only seats changes.
    existing = svc.get_subscription(org_id=user.org_id)
    plan_code = body.plan_code or (existing.plan_code if existing else None)
    if plan_code is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="plan_code required",
        )
    try:
        plan = get_plan(plan_code)
    except UnknownPlan:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Unknown plan: {plan_code}",
        )
    seats = body.seats if body.seats is not None else (
        existing.seats if existing else 1
    )

    org_name = getattr(user, "email", str(user.org_id))
    try:
        row = await svc.set_plan(
            org_id=user.org_id,
            org_name=org_name,
            plan=plan,
            seats=seats,
            org_email=getattr(user, "email", None),
        )
    except BillingProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    db.commit()
    return _to_sub_out(row)


# ── Invoices ────────────────────────────────────────────────────────────────


@router.get("/invoices", response_model=InvoiceList)
def list_invoices(
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
    limit: int = 50,
) -> InvoiceList:
    svc = BillingService(db, provider)
    rows = svc.list_invoices(org_id=user.org_id, limit=limit)
    return InvoiceList(items=[_to_inv_out(r) for r in rows])


# ── Webhook ─────────────────────────────────────────────────────────────────


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
) -> dict:
    """Receive a Stripe webhook.

    Verifies signature against ``STRIPE_WEBHOOK_SECRET`` and applies the
    event via :class:`BillingService`. Returns ``{"received": True}`` per
    Stripe's recommendation. Non-Stripe providers respond with 501.
    """
    if not isinstance(provider, StripeBillingProvider):
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            detail="webhook receiver only supported for the Stripe provider",
        )
    if not stripe_signature:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="missing Stripe-Signature header",
        )
    payload = await request.body()
    try:
        event = provider.verify_webhook(
            payload=payload, sig_header=stripe_signature,
        )
    except BillingProviderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))

    svc = BillingService(db, provider)
    tag = svc.apply_webhook_event(event)
    db.commit()
    logger.info("billing.webhook applied tag=%s type=%s", tag, event.get("type"))
    return {"received": True, "tag": tag}
