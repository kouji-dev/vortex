"""Webhooks API — /v1/webhooks/*

Endpoints (org-scoped, owner/admin only):
- GET    /v1/webhooks                       — list registered webhooks
- POST   /v1/webhooks                       — register new webhook (returns secret once)
- PATCH  /v1/webhooks/{id}                  — update url / event types / enabled
- DELETE /v1/webhooks/{id}                  — remove webhook
- GET    /v1/webhooks/{id}/deliveries       — recent delivery attempts
- POST   /v1/webhooks/{id}/deliveries/{did}/replay — re-enqueue the payload
- GET    /v1/webhook-event-types            — catalog of registerable event keys
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.webhooks import event_types as event_types_registry
from ai_portal.webhooks.schemas import (
    WebhookCreate,
    WebhookCreated,
    WebhookDeliveriesList,
    WebhookDeliveryOut,
    WebhookEventTypeOut,
    WebhookEventTypesList,
    WebhookOut,
    WebhookUpdate,
)
from ai_portal.webhooks.service import (
    DeliveryNotFound,
    UnknownEventType,
    WebhookNotFound,
    WebhookService,
)

router = APIRouter(prefix="/v1", tags=["webhooks"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, "owner", "admin")
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org context")
    return user


def _to_out(webhook) -> WebhookOut:
    return WebhookOut(
        id=webhook.id,
        org_id=webhook.org_id,
        url=webhook.url,
        event_types=webhook.event_types_json or [],
        enabled=webhook.enabled,
        description=webhook.description,
        created_at=webhook.created_at,
        disabled_at=webhook.disabled_at,
    )


def _to_delivery_out(row) -> WebhookDeliveryOut:
    return WebhookDeliveryOut(
        id=row.id,
        webhook_id=row.webhook_id,
        event_id=row.event_id,
        event_type=row.event_type,
        status=row.status,
        attempts=row.attempts,
        last_response_status=row.last_response_status,
        last_response_body=row.last_response_body,
        last_error=row.last_error,
        next_attempt_at=row.next_attempt_at,
        delivered_at=row.delivered_at,
        failed_at=row.failed_at,
        created_at=row.created_at,
    )


# ── Webhook CRUD ────────────────────────────────────────────────────────────


@router.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> list[WebhookOut]:
    svc = WebhookService(db)
    return [_to_out(w) for w in svc.list(org_id=user.org_id)]


@router.post(
    "/webhooks",
    response_model=WebhookCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_webhook(
    body: WebhookCreate,
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> WebhookCreated:
    svc = WebhookService(db)
    try:
        webhook, secret = svc.create(
            org_id=user.org_id,
            url=str(body.url),
            event_types=body.event_types,
            description=body.description,
        )
    except UnknownEventType as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"unknown event type(s): {e}",
        ) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    db.commit()
    out = _to_out(webhook)
    return WebhookCreated(**out.model_dump(), secret=secret)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
def update_webhook(
    webhook_id: _uuid.UUID,
    body: WebhookUpdate,
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> WebhookOut:
    svc = WebhookService(db)
    try:
        webhook = svc.update(
            org_id=user.org_id,
            webhook_id=webhook_id,
            url=str(body.url) if body.url is not None else None,
            event_types=body.event_types,
            description=body.description,
            enabled=body.enabled,
        )
    except WebhookNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="webhook not found") from e
    except UnknownEventType as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"unknown event type(s): {e}",
        ) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    db.commit()
    return _to_out(webhook)


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: _uuid.UUID,
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> None:
    svc = WebhookService(db)
    try:
        svc.delete(org_id=user.org_id, webhook_id=webhook_id)
    except WebhookNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="webhook not found") from e
    db.commit()


# ── Deliveries ──────────────────────────────────────────────────────────────


@router.get(
    "/webhooks/{webhook_id}/deliveries",
    response_model=WebhookDeliveriesList,
)
def list_deliveries(
    webhook_id: _uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> WebhookDeliveriesList:
    svc = WebhookService(db)
    try:
        rows = svc.list_deliveries(
            org_id=user.org_id,
            webhook_id=webhook_id,
            limit=limit,
            offset=offset,
        )
    except WebhookNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="webhook not found") from e
    return WebhookDeliveriesList(
        items=[_to_delivery_out(r) for r in rows],
        total=len(rows),
    )


@router.post(
    "/webhooks/{webhook_id}/deliveries/{delivery_id}/replay",
    response_model=WebhookDeliveryOut,
    status_code=status.HTTP_201_CREATED,
)
def replay_delivery(
    webhook_id: _uuid.UUID,
    delivery_id: _uuid.UUID,
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> WebhookDeliveryOut:
    svc = WebhookService(db)
    try:
        new_row = svc.replay_delivery(
            org_id=user.org_id,
            webhook_id=webhook_id,
            delivery_id=delivery_id,
        )
    except WebhookNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="webhook not found") from e
    except DeliveryNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="delivery not found") from e
    db.commit()
    return _to_delivery_out(new_row)


# ── Event type catalog ──────────────────────────────────────────────────────


@router.get("/webhook-event-types", response_model=WebhookEventTypesList)
def list_event_types() -> WebhookEventTypesList:
    return WebhookEventTypesList(
        items=[
            WebhookEventTypeOut(
                key=et.key, description=et.description, module=et.module
            )
            for et in event_types_registry.list_event_types()
        ]
    )
