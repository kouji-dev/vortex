"""WebhookService — registration + emit_webhook fan-out + delivery accessors.

A delivery row is created per (webhook, event) pair; the asyncio worker in
:mod:`ai_portal.webhooks.worker` drives the actual HTTP send.

Secret handling:
- ``secret`` (plaintext) returned once on create
- ``secret_hash`` (SHA-256 hex) stored for diagnostics + verification
- ``secret_encrypted`` stored verbatim for MVP (DB-level at-rest crypto)
  TODO: wrap with KMS/app-level cipher when control plane key mgmt lands.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import uuid as _uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.webhooks import event_types as event_types_registry
from ai_portal.webhooks.model import Webhook, WebhookDelivery
from ai_portal.webhooks.worker import (
    DeliveryResult,
    _PendingDelivery,
    next_attempt_at,
)

logger = logging.getLogger(__name__)


# ── Errors ───────────────────────────────────────────────────────────────────


class WebhookNotFound(Exception):
    """Raised when a webhook id is not present in the calling org."""


class UnknownEventType(Exception):
    """Raised when a caller subscribes to / emits an unregistered event type."""


class DeliveryNotFound(Exception):
    pass


# ── Secret helpers ───────────────────────────────────────────────────────────


_SECRET_PREFIX = "whsec_"


def _new_secret() -> str:
    """Mint a fresh signing secret. Format: ``whsec_<32 url-safe base64 chars>``."""
    return _SECRET_PREFIX + base64.urlsafe_b64encode(secrets.token_bytes(24)).rstrip(b"=").decode()


def _hash_secret(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


# ── Service ──────────────────────────────────────────────────────────────────


class WebhookService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── CRUD ────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        org_id: _uuid.UUID,
        url: str,
        event_types: Iterable[str],
        description: str | None = None,
    ) -> tuple[Webhook, str]:
        event_types_list = list(dict.fromkeys(event_types))  # de-dup, preserve order
        if not event_types_list:
            raise ValueError("event_types required")
        self._validate_event_types(event_types_list)

        secret = _new_secret()
        webhook = Webhook(
            org_id=org_id,
            url=str(url),
            secret_hash=_hash_secret(secret),
            secret_encrypted=secret,
            event_types_json=event_types_list,
            enabled=True,
            description=description,
        )
        self.db.add(webhook)
        self.db.flush()
        return webhook, secret

    def get(self, *, org_id: _uuid.UUID, webhook_id: _uuid.UUID) -> Webhook:
        webhook = self.db.scalars(
            select(Webhook).where(
                Webhook.id == webhook_id, Webhook.org_id == org_id
            )
        ).first()
        if webhook is None:
            raise WebhookNotFound(str(webhook_id))
        return webhook

    def list(self, *, org_id: _uuid.UUID) -> list[Webhook]:
        return list(
            self.db.scalars(
                select(Webhook)
                .where(Webhook.org_id == org_id)
                .order_by(Webhook.created_at.desc())
            )
        )

    def update(
        self,
        *,
        org_id: _uuid.UUID,
        webhook_id: _uuid.UUID,
        url: str | None = None,
        event_types: Iterable[str] | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> Webhook:
        webhook = self.get(org_id=org_id, webhook_id=webhook_id)
        if url is not None:
            webhook.url = str(url)
        if event_types is not None:
            et_list = list(dict.fromkeys(event_types))
            if not et_list:
                raise ValueError("event_types must be non-empty")
            self._validate_event_types(et_list)
            webhook.event_types_json = et_list
        if description is not None:
            webhook.description = description
        if enabled is not None:
            webhook.enabled = enabled
            webhook.disabled_at = None if enabled else datetime.now(UTC)
        self.db.flush()
        return webhook

    def delete(self, *, org_id: _uuid.UUID, webhook_id: _uuid.UUID) -> None:
        webhook = self.get(org_id=org_id, webhook_id=webhook_id)
        self.db.delete(webhook)
        self.db.flush()

    # ── emit_webhook ────────────────────────────────────────────────────

    def emit_webhook(
        self,
        *,
        event_type: str,
        payload: dict,
        org_id: _uuid.UUID,
        event_id: _uuid.UUID | None = None,
    ) -> list[WebhookDelivery]:
        """Enqueue a delivery row for every enabled webhook subscribed to ``event_type``.

        Returns the list of created ``WebhookDelivery`` rows (one per webhook).
        Returns an empty list when no webhook subscribes — emit is a no-op.

        Raises :class:`UnknownEventType` if ``event_type`` is not registered.
        """
        if not event_types_registry.is_registered(event_type):
            raise UnknownEventType(event_type)

        webhooks = self.db.scalars(
            select(Webhook).where(
                Webhook.org_id == org_id,
                Webhook.enabled.is_(True),
            )
        ).all()
        subscribed = [
            w for w in webhooks if event_type in (w.event_types_json or [])
        ]
        if not subscribed:
            return []

        event_id = event_id or _uuid.uuid4()
        now = datetime.now(UTC)
        deliveries: list[WebhookDelivery] = []
        for w in subscribed:
            d = WebhookDelivery(
                webhook_id=w.id,
                org_id=org_id,
                event_id=event_id,
                event_type=event_type,
                payload_json=payload,
                status="pending",
                attempts=0,
                next_attempt_at=now,  # immediately eligible for worker pickup
            )
            self.db.add(d)
            deliveries.append(d)
        self.db.flush()
        logger.info(
            "emit_webhook event_type=%s org=%s subscribers=%d",
            event_type,
            org_id,
            len(deliveries),
        )
        return deliveries

    # ── Delivery accessors (used by worker + router) ───────────────────

    def list_deliveries(
        self,
        *,
        org_id: _uuid.UUID,
        webhook_id: _uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WebhookDelivery]:
        # Confirm webhook ownership (raises WebhookNotFound otherwise).
        self.get(org_id=org_id, webhook_id=webhook_id)
        return list(
            self.db.scalars(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.webhook_id == webhook_id,
                    WebhookDelivery.org_id == org_id,
                )
                .order_by(WebhookDelivery.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    def get_delivery(
        self,
        *,
        org_id: _uuid.UUID,
        webhook_id: _uuid.UUID,
        delivery_id: _uuid.UUID,
    ) -> WebhookDelivery:
        self.get(org_id=org_id, webhook_id=webhook_id)
        row = self.db.scalars(
            select(WebhookDelivery).where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.webhook_id == webhook_id,
                WebhookDelivery.org_id == org_id,
            )
        ).first()
        if row is None:
            raise DeliveryNotFound(str(delivery_id))
        return row

    def replay_delivery(
        self,
        *,
        org_id: _uuid.UUID,
        webhook_id: _uuid.UUID,
        delivery_id: _uuid.UUID,
    ) -> WebhookDelivery:
        """Enqueue a new delivery row carrying the same payload + event id.

        Re-uses the original ``event_id`` so the receiver can dedupe but treats
        the replay as a fresh attempt (``attempts=0``, ``status=pending``).
        """
        original = self.get_delivery(
            org_id=org_id, webhook_id=webhook_id, delivery_id=delivery_id
        )
        replay = WebhookDelivery(
            webhook_id=original.webhook_id,
            org_id=org_id,
            event_id=original.event_id,
            event_type=original.event_type,
            payload_json=original.payload_json,
            status="pending",
            attempts=0,
            next_attempt_at=datetime.now(UTC),
        )
        self.db.add(replay)
        self.db.flush()
        return replay

    # ── Worker hooks ───────────────────────────────────────────────────

    def fetch_due_deliveries(
        self, now: datetime, *, limit: int = 100
    ) -> list[_PendingDelivery]:
        """Return rows whose ``next_attempt_at`` ≤ now and status is retryable."""
        rows = self.db.scalars(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status.in_(("pending", "in_flight")),
                WebhookDelivery.next_attempt_at.is_not(None),
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at.asc())
            .limit(limit)
        ).all()

        out: list[_PendingDelivery] = []
        for row in rows:
            webhook = self.db.get(Webhook, row.webhook_id)
            if webhook is None or not webhook.enabled:
                # Webhook revoked between enqueue + pick-up.
                row.status = "failed"
                row.failed_at = now
                row.last_error = "webhook disabled"
                row.next_attempt_at = None
                continue
            out.append(
                _PendingDelivery(
                    id=row.id,
                    webhook_id=row.webhook_id,
                    org_id=row.org_id,
                    event_id=row.event_id,
                    event_type=row.event_type,
                    payload=row.payload_json,
                    url=webhook.url,
                    secret=webhook.secret_encrypted.encode("utf-8"),
                    attempts=row.attempts,
                )
            )
        if out:
            self.db.flush()
        return out

    def record_delivery_success(
        self, delivery_id: _uuid.UUID, result: DeliveryResult
    ) -> None:
        row = self.db.get(WebhookDelivery, delivery_id)
        if row is None:
            raise DeliveryNotFound(str(delivery_id))
        now = datetime.now(UTC)
        row.status = "delivered"
        row.attempts = row.attempts + 1
        row.last_response_status = result.status_code
        row.last_response_body = result.body
        row.last_error = None
        row.next_attempt_at = None
        row.delivered_at = now
        self.db.flush()

    def record_delivery_failure(
        self,
        delivery_id: _uuid.UUID,
        result: DeliveryResult,
        next_at: datetime | None,
        permanent: bool,
    ) -> None:
        row = self.db.get(WebhookDelivery, delivery_id)
        if row is None:
            raise DeliveryNotFound(str(delivery_id))
        row.attempts = row.attempts + 1
        row.last_response_status = result.status_code
        row.last_response_body = result.body
        row.last_error = result.error
        if permanent:
            row.status = "failed"
            row.failed_at = datetime.now(UTC)
            row.next_attempt_at = None
        else:
            row.status = "pending"
            row.next_attempt_at = next_at
        self.db.flush()

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _validate_event_types(et_list: list[str]) -> None:
        unknown = [k for k in et_list if not event_types_registry.is_registered(k)]
        if unknown:
            raise UnknownEventType(", ".join(unknown))


# ── Module-level convenience ────────────────────────────────────────────────


def emit_webhook(
    db: Session,
    *,
    event_type: str,
    payload: dict,
    org_id: _uuid.UUID,
    event_id: _uuid.UUID | None = None,
) -> list[WebhookDelivery]:
    """Module-level ``emit_webhook`` for callers that don't hold a service.

    Re-export of :meth:`WebhookService.emit_webhook` keyed on a session.
    """
    return WebhookService(db).emit_webhook(
        event_type=event_type, payload=payload, org_id=org_id, event_id=event_id
    )


# Re-export for ``next_attempt_at`` convenience in callers.
__all__ = [
    "DeliveryNotFound",
    "UnknownEventType",
    "WebhookNotFound",
    "WebhookService",
    "emit_webhook",
    "next_attempt_at",
]
