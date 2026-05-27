"""AWS SES channel — Jinja2 template + boto3 SES client.

Synchronous boto3 call wrapped in async signature. Production-ready transactional
mail for AWS deployments.
"""

from __future__ import annotations

from dataclasses import dataclass

import boto3

from ai_portal.notify.templating import render


@dataclass(slots=True)
class SesConfig:
    region: str
    from_addr: str
    access_key_id: str | None = None
    secret_access_key: str | None = None


class SesChannel:
    """Render Jinja2 template and send via AWS SES."""

    def __init__(self, config: SesConfig) -> None:
        self._cfg = config
        kwargs: dict = {"region_name": config.region}
        if config.access_key_id and config.secret_access_key:
            kwargs["aws_access_key_id"] = config.access_key_id
            kwargs["aws_secret_access_key"] = config.secret_access_key
        self._client = boto3.client("ses", **kwargs)

    async def send(
        self,
        recipient: str,
        template_id: str,
        payload: dict,
    ) -> None:
        subject = render(template_id, "subject", payload)
        body = render(template_id, "body", payload)

        self._client.send_email(
            Source=self._cfg.from_addr,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
