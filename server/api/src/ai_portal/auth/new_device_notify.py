"""Bridge: auth/sessions new-device hook → notify.send_event.

Application startup calls :func:`install_new_device_notifier` with a configured
:class:`NotifyService`. When a new device logs in, ``create_session`` invokes
the hook synchronously; the hook schedules an async ``send_event`` on the
running loop so the login response is not blocked on transport latency.

Decoupled from sessions.py so the auth module does not import the notify
subsystem at module-load time.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ai_portal.auth.sessions import set_new_device_hook
from ai_portal.notify.service import NotifyService

logger = logging.getLogger(__name__)

NEW_DEVICE_EVENT_TYPE = "auth.login.new_device"
NEW_DEVICE_TEMPLATE_ID = "auth_login_new_device"


def install_new_device_notifier(notify: NotifyService) -> None:
    """Wire the sessions hook to fire ``notify.send_event`` on new device login."""

    def _hook(user_id: int, ip: str | None, user_agent: str | None, ts: datetime) -> None:
        payload = {
            "ip": ip or "",
            "user_agent": user_agent or "",
            "ts": ts.isoformat(),
        }
        coro = notify.send_event(
            user_id=user_id,
            event_type=NEW_DEVICE_EVENT_TYPE,
            template_id=NEW_DEVICE_TEMPLATE_ID,
            payload=payload,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop — synchronous context (background worker, test).
            # Fire-and-forget via asyncio.run is dangerous; log + drop.
            logger.warning(
                "new_device_notifier: no running loop, dropping event user_id=%s", user_id
            )
            coro.close()
            return
        loop.create_task(coro)

    set_new_device_hook(_hook)
