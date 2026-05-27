"""SMTP channel — Jinja2 template + smtplib dispatch.

Synchronous smtplib wrapped in async signature; intended for low-volume
transactional mail. Production deployments should switch to ses/sendgrid.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from ai_portal.notify.templating import render


@dataclass(slots=True)
class SmtpConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    from_addr: str
    use_tls: bool = True


class SmtpChannel:
    """Render Jinja2 template and send via SMTP."""

    def __init__(self, config: SmtpConfig) -> None:
        self._cfg = config

    async def send(
        self,
        recipient: str,
        template_id: str,
        payload: dict,
    ) -> None:
        subject = render(template_id, "subject", payload)
        body = render(template_id, "body", payload)

        msg = EmailMessage()
        msg["From"] = self._cfg.from_addr
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(self._cfg.host, self._cfg.port) as smtp:
            if self._cfg.use_tls:
                smtp.starttls()
            if self._cfg.username and self._cfg.password:
                smtp.login(self._cfg.username, self._cfg.password)
            smtp.send_message(msg)
