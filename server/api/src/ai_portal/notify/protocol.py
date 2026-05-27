"""Channel protocol.

Every notification channel implements ``send(recipient, template_id, payload)``.
Recipient format depends on channel:
- smtp / ses / sendgrid: email address
- slack_webhook: webhook URL
- in_app: ``user:<id>:<org_uuid>``
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Channel(Protocol):
    """Notification channel contract.

    Implementations:
    - render template_id with payload
    - dispatch via channel-specific transport
    - raise on hard failures (caller decides retry policy)
    """

    async def send(
        self,
        recipient: str,
        template_id: str,
        payload: dict,
    ) -> None: ...
