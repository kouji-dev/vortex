"""Bundled notification channels."""

from ai_portal.notify.channels.in_app import InAppChannel
from ai_portal.notify.channels.smtp import SmtpChannel, SmtpConfig

__all__ = ["InAppChannel", "SmtpChannel", "SmtpConfig"]
