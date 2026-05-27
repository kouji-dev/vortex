"""WebhookService.emit_webhook — fan-out + replay + delivery accessors.

Requires Postgres (skips when DATABASE_URL is absent) — the service exercises
RLS columns + JSONB filters that sqlite cannot model.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_postgres


@requires_postgres
def test_emit_webhook_fans_out_to_subscribers() -> None:
    """Two webhooks subscribed → two delivery rows. One unrelated → no row."""
    from ai_portal.auth.model import Org
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.webhooks.model import WebhookDelivery
    from ai_portal.webhooks.service import WebhookService

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.add(Org(id=org_id, slug=f"e2e-{uuid.uuid4().hex[:8]}", name="emit-test"))
            db.flush()

            svc = WebhookService(db)
            sub1, _ = svc.create(
                org_id=org_id,
                url="https://hook1.test/in",
                event_types=["budget.exceeded", "budget.warning"],
            )
            sub2, _ = svc.create(
                org_id=org_id,
                url="https://hook2.test/in",
                event_types=["budget.exceeded"],
            )
            unrelated, _ = svc.create(
                org_id=org_id,
                url="https://hook3.test/in",
                event_types=["gateway.policy.violation"],
            )
            db.flush()

            deliveries = svc.emit_webhook(
                event_type="budget.exceeded",
                payload={"limit_cents": 1000, "used_cents": 1050},
                org_id=org_id,
            )

            assert len(deliveries) == 2
            webhook_ids = {d.webhook_id for d in deliveries}
            assert webhook_ids == {sub1.id, sub2.id}
            for d in deliveries:
                assert d.event_type == "budget.exceeded"
                assert d.status == "pending"
                assert d.attempts == 0
                assert d.next_attempt_at is not None
                assert d.payload_json == {"limit_cents": 1000, "used_cents": 1050}
            event_ids = {d.event_id for d in deliveries}
            assert len(event_ids) == 1  # same event_id for the same emit

            # Unrelated webhook gets no delivery row.
            unrelated_rows = (
                db.query(WebhookDelivery)
                .filter(WebhookDelivery.webhook_id == unrelated.id)
                .all()
            )
            assert unrelated_rows == []
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_emit_webhook_returns_empty_when_no_subscribers() -> None:
    from ai_portal.auth.model import Org
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.webhooks.service import WebhookService

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.add(Org(id=org_id, slug=f"e2e-{uuid.uuid4().hex[:8]}", name="no-sub"))
            db.flush()
            svc = WebhookService(db)
            assert (
                svc.emit_webhook(
                    event_type="api_key.created", payload={}, org_id=org_id
                )
                == []
            )
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_emit_webhook_rejects_unknown_event_type() -> None:
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.webhooks.service import UnknownEventType, WebhookService

    db = SessionLocal()
    try:
        svc = WebhookService(db)
        with pytest.raises(UnknownEventType):
            svc.emit_webhook(
                event_type="nope.does.not.exist",
                payload={},
                org_id=uuid.uuid4(),
            )
    finally:
        db.close()


@requires_postgres
def test_emit_webhook_skips_disabled_webhook() -> None:
    from ai_portal.auth.model import Org
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.webhooks.service import WebhookService

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.add(Org(id=org_id, slug=f"e2e-{uuid.uuid4().hex[:8]}", name="disabled"))
            db.flush()
            svc = WebhookService(db)
            wh, _ = svc.create(
                org_id=org_id,
                url="https://hook.test/x",
                event_types=["api_key.revoked"],
            )
            db.flush()
            svc.update(org_id=org_id, webhook_id=wh.id, enabled=False)
            db.flush()

            deliveries = svc.emit_webhook(
                event_type="api_key.revoked", payload={}, org_id=org_id
            )
            assert deliveries == []
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_replay_delivery_clones_event() -> None:
    from ai_portal.auth.model import Org
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.webhooks.service import WebhookService

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.add(Org(id=org_id, slug=f"e2e-{uuid.uuid4().hex[:8]}", name="replay"))
            db.flush()
            svc = WebhookService(db)
            wh, _ = svc.create(
                org_id=org_id,
                url="https://hook.test/replay",
                event_types=["budget.warning"],
            )
            db.flush()
            (original,) = svc.emit_webhook(
                event_type="budget.warning",
                payload={"pct": 80},
                org_id=org_id,
            )
            db.flush()

            replay = svc.replay_delivery(
                org_id=org_id,
                webhook_id=wh.id,
                delivery_id=original.id,
            )
            assert replay.id != original.id
            assert replay.event_id == original.event_id
            assert replay.event_type == original.event_type
            assert replay.payload_json == original.payload_json
            assert replay.status == "pending"
            assert replay.attempts == 0
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_emit_webhook_module_function_matches_service() -> None:
    from ai_portal.auth.model import Org
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.webhooks import emit_webhook as emit_fn
    from ai_portal.webhooks.service import WebhookService

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.add(Org(id=org_id, slug=f"e2e-{uuid.uuid4().hex[:8]}", name="module-fn"))
            db.flush()
            WebhookService(db).create(
                org_id=org_id,
                url="https://hook.test/fn",
                event_types=["org.member.added"],
            )
            db.flush()
            deliveries = emit_fn(
                db,
                event_type="org.member.added",
                payload={"user_id": 7},
                org_id=org_id,
            )
            assert len(deliveries) == 1
    finally:
        db.rollback()
        db.close()
