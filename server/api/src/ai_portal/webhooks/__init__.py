"""Webhooks subsystem — outbound HTTP delivery with HMAC signing.

Exposed primitives:
- ``sign_payload`` / ``verify_signature`` — HMAC-SHA256, ``v1=<hex>``
- ``Webhook``, ``WebhookDelivery``, ``WebhookEventType`` (ORM)
- ``WebhookService`` + ``emit_webhook(event_type, payload, org_id)``
- ``register_event_type`` — modules register their event types at import time
- ``DeliveryWorker`` — asyncio task with exponential backoff up to 24h
"""

from ai_portal.webhooks.event_types import (
    EventTypeAlreadyRegistered,
    list_event_types,
    register_event_type,
)
from ai_portal.webhooks.signer import sign_payload, verify_signature

__all__ = [
    "EventTypeAlreadyRegistered",
    "list_event_types",
    "register_event_type",
    "sign_payload",
    "verify_signature",
]
