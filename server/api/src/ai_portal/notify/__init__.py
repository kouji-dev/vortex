"""Notification subsystem — channel protocol + bundled channels + service.

Exposed primitives:
- ``Channel`` (protocol)
- ``NotifyService``
- ``InAppChannel``, ``SmtpChannel``
- ``Notification``, ``UserNotificationPref`` (ORM)
"""

from ai_portal.notify.protocol import Channel
from ai_portal.notify.service import NotifyService

__all__ = ["Channel", "NotifyService"]
