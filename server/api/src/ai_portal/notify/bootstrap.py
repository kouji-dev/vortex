"""Build a NotifyService from current app settings.

Called from app lifespan so the notify subsystem can be wired exactly once at
startup. Returns ``None`` when no transport is configured — callers must skip
hook installation in that case.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ai_portal.notify.channels import InAppChannel
from ai_portal.notify.service import NotifyService

logger = logging.getLogger(__name__)


def _maybe_smtp_channel(settings: Any):
    host = getattr(settings, "smtp_host", "") or ""
    if not host:
        return None
    try:
        from ai_portal.notify.channels.smtp import SmtpChannel, SmtpConfig

        return SmtpChannel(
            SmtpConfig(
                host=host,
                port=int(getattr(settings, "smtp_port", 587) or 587),
                username=getattr(settings, "smtp_user", "") or None,
                password=getattr(settings, "smtp_password", "") or None,
                from_addr=os.environ.get("SMTP_FROM", "no-reply@ai-portal.local"),
                use_tls=True,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("smtp_channel_init_failed: %s", exc)
        return None


def _maybe_sendgrid_channel():
    api_key = os.environ.get("SENDGRID_API_KEY", "")
    from_addr = os.environ.get("SENDGRID_FROM", "")
    if not api_key or not from_addr:
        return None
    try:
        from ai_portal.notify.channels.sendgrid import (
            SendgridChannel,
            SendgridConfig,
        )

        return SendgridChannel(
            SendgridConfig(
                api_key=api_key,
                from_addr=from_addr,
                from_name=os.environ.get("SENDGRID_FROM_NAME") or None,
                sandbox=os.environ.get("SENDGRID_SANDBOX", "").lower()
                in {"1", "true", "yes"},
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sendgrid_channel_init_failed: %s", exc)
        return None


def build_notify_service(settings: Any) -> NotifyService | None:
    """Construct a NotifyService with whatever channels are configured.

    Returns ``None`` if no usable transport exists (not even in-app). When at
    least one transport is configured (SMTP / SendGrid), an InApp channel is
    added too — in-app delivery is cheap and lives in our own DB so it has no
    runtime requirements.
    """
    channels: dict[str, Any] = {}
    smtp = _maybe_smtp_channel(settings)
    if smtp is not None:
        channels["email"] = smtp
    sg = _maybe_sendgrid_channel()
    if sg is not None:
        channels.setdefault("email", sg)
    if not channels:
        return None
    try:
        from ai_portal.core.db.session import SessionLocal

        channels["in_app"] = InAppChannel(SessionLocal)
    except Exception as exc:  # noqa: BLE001
        logger.warning("in_app_channel_init_failed: %s", exc)
    return NotifyService(channels)
