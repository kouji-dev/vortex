"""Notification subsystem — channel protocol + bundled channels + service.

Exposed primitives:
- ``Channel`` (protocol)
- ``NotifyService`` — fan-out dispatcher with per-user preference matrix
- ``send_event(service, user_id, event_type, template_id, payload)`` —
  module-level thin wrapper around ``NotifyService.send_event`` so callers
  don't have to remember the keyword-only call shape

Channel implementations live under ``ai_portal.notify.channels``.
"""

from __future__ import annotations

from ai_portal.notify.protocol import Channel
from ai_portal.notify.service import NotifyService


async def send_event(
    service: NotifyService,
    *,
    user_id: int,
    event_type: str,
    template_id: str,
    payload: dict,
) -> None:
    """Dispatch ``event_type`` to a user across their enabled channels.

    Thin wrapper around :meth:`NotifyService.send_event` for callers that
    import via the control-plane facade.
    """
    await service.send_event(
        user_id=user_id,
        event_type=event_type,
        template_id=template_id,
        payload=payload,
    )


__all__ = ["Channel", "NotifyService", "send_event"]
