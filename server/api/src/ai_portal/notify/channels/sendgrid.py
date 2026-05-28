"""SendGrid channel — Jinja2 template + SendGrid v3 mail/send HTTP API.

Async httpx POST; production-grade transactional mail for deployments that
prefer SendGrid over AWS SES or vanilla SMTP.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ai_portal.notify.templating import render

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"
DEFAULT_TIMEOUT_S = 10.0


@dataclass(slots=True)
class SendgridConfig:
    api_key: str
    from_addr: str
    from_name: str | None = None
    sandbox: bool = False
    base_url: str = SENDGRID_API_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_S


class SendgridSendFailed(RuntimeError):
    """Raised when SendGrid returns a non-2xx response."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"sendgrid send failed: HTTP {status_code} body={body!r}")
        self.status_code = status_code
        self.body = body


class SendgridChannel:
    """Render Jinja2 template and dispatch via SendGrid v3 mail/send."""

    def __init__(
        self,
        config: SendgridConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._cfg = config
        self._client = client  # injected in tests; production opens per-send

    def _payload(self, recipient: str, subject: str, body: str) -> dict:
        from_obj: dict = {"email": self._cfg.from_addr}
        if self._cfg.from_name:
            from_obj["name"] = self._cfg.from_name
        payload: dict = {
            "personalizations": [{"to": [{"email": recipient}]}],
            "from": from_obj,
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }
        if self._cfg.sandbox:
            payload["mail_settings"] = {"sandbox_mode": {"enable": True}}
        return payload

    async def send(
        self,
        recipient: str,
        template_id: str,
        payload: dict,
    ) -> None:
        subject = render(template_id, "subject", payload)
        body = render(template_id, "body", payload)
        wire = self._payload(recipient, subject, body)
        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            resp = await self._client.post(
                self._cfg.base_url, json=wire, headers=headers
            )
        else:
            async with httpx.AsyncClient(timeout=self._cfg.timeout_seconds) as client:
                resp = await client.post(
                    self._cfg.base_url, json=wire, headers=headers
                )
        if resp.status_code >= 300:
            raise SendgridSendFailed(resp.status_code, resp.text)
