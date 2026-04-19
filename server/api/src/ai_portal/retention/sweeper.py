"""Retention sweeper — deletes expired data per org policy.

Run via RQ worker or as a daily cron job::

    python scripts/run_retention_worker.py

Never runs when ``retention_policy.legal_hold`` is true.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.core.db.rls import bypass_rls

logger = logging.getLogger(__name__)


def sweep_all_orgs(db: Session) -> None:
    """Sweep expired data for every org that has a retention policy."""
    from ai_portal.retention.model import RetentionPolicy  # noqa: PLC0415

    with bypass_rls(db):
        policies = db.scalars(select(RetentionPolicy)).all()

    for policy in policies:
        if policy.legal_hold:
            logger.info("retention_sweeper: skipping org=%s (legal_hold=true)", policy.org_id)
            continue
        sweep_org(db, policy)


def sweep_org(db: Session, policy: "RetentionPolicy") -> None:
    from ai_portal.chat.model import ChatConversation, ChatUpload  # noqa: PLC0415
    from ai_portal.usage.model import MessageUsage, UsageRollup  # noqa: PLC0415
    from ai_portal.audit.model import AuditEvent  # noqa: PLC0415

    now = datetime.now(UTC)

    with bypass_rls(db):
        # ── Conversations + cascaded messages ─────────────────────────────────
        if policy.conversation_retention_days is not None:
            cutoff = now - timedelta(days=policy.conversation_retention_days)
            old_convs = db.scalars(
                select(ChatConversation).where(
                    ChatConversation.org_id == policy.org_id,
                    ChatConversation.created_at < cutoff,
                )
            ).all()
            for conv in old_convs:
                # Delete uploads on disk before cascading the DB row.
                uploads = db.scalars(
                    select(ChatUpload).where(
                        ChatUpload.conversation_id == conv.id,
                        ChatUpload.legal_hold.is_(False),
                    )
                ).all()
                for upload in uploads:
                    _delete_upload_file(upload.stored_path)
                    db.delete(upload)
                db.delete(conv)
            if old_convs:
                db.commit()
                logger.info("retention_sweeper: deleted %d conversations for org=%s", len(old_convs), policy.org_id)

        # ── Uploads past upload retention ────────────────────────────────────
        if policy.upload_retention_days is not None:
            cutoff = now - timedelta(days=policy.upload_retention_days)
            old_uploads = db.scalars(
                select(ChatUpload).where(
                    ChatUpload.org_id == policy.org_id,
                    ChatUpload.created_at < cutoff,
                    ChatUpload.legal_hold.is_(False),
                )
            ).all()
            for upload in old_uploads:
                _delete_upload_file(upload.stored_path)
                db.delete(upload)
            if old_uploads:
                db.commit()
                logger.info("retention_sweeper: deleted %d orphan uploads for org=%s", len(old_uploads), policy.org_id)

        # ── Usage rollup ─────────────────────────────────────────────────────
        usage_cutoff = now - timedelta(days=policy.usage_retention_days)
        deleted_usage = db.execute(
            select(MessageUsage.id).where(
                MessageUsage.org_id == policy.org_id,
                MessageUsage.created_at < usage_cutoff,
            ).limit(10_000)
        ).scalars().all()
        if deleted_usage:
            db.execute(
                MessageUsage.__table__.delete().where(MessageUsage.id.in_(deleted_usage))
            )
            db.commit()
            logger.info("retention_sweeper: deleted %d usage rows for org=%s", len(deleted_usage), policy.org_id)

        # ── Audit events ─────────────────────────────────────────────────────
        audit_cutoff = now - timedelta(days=policy.audit_retention_days)
        deleted_audit = db.execute(
            select(AuditEvent.id).where(
                AuditEvent.org_id == policy.org_id,
                AuditEvent.created_at < audit_cutoff,
            ).limit(10_000)
        ).scalars().all()
        if deleted_audit:
            # Bypass immutability trigger by keeping bypass_rls context.
            db.execute(
                AuditEvent.__table__.delete().where(AuditEvent.id.in_(deleted_audit))
            )
            db.commit()
            logger.info("retention_sweeper: deleted %d audit rows for org=%s", len(deleted_audit), policy.org_id)


def _delete_upload_file(stored_path: str) -> None:
    try:
        p = Path(stored_path)
        if p.exists():
            p.unlink()
    except Exception as exc:  # noqa: BLE001
        logger.warning("retention_sweeper: failed to delete file %s: %s", stored_path, exc)
