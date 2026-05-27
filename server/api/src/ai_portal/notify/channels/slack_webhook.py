"""Slack incoming-webhook channel.

Recipient is the webhook URL (https://hooks.slack.com/services/...). Renders the
template body and posts as ``{"text": ...}``. Transport overridable for tests.
"""

from __future__ import annotations

import httpx

from ai_portal.notify.templating import render

_ALLOWED_PREFIX = "https://hooks.slack.com/"


class SlackWebhookChannel:
    """Post rendered template body to a Slack incoming webhook URL."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._transport = transport
        self._timeout_s = timeout_s

    async def send(
        self,
        recipient: str,
        template_id: str,
        payload: dict,
    ) -> None:
        if not recipient.startswith(_ALLOWED_PREFIX):
            raise ValueError(
                f"slack_webhook recipient must start with {_ALLOWED_PREFIX!r}, "
                f"got: {recipient!r}"
            )

        body = render(template_id, "body", payload)

        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout_s,
        ) as client:
            resp = await client.post(recipient, json={"text": body})
            resp.raise_for_status()
