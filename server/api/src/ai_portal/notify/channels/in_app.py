"""In-app channel — persists a Notification row.

Recipient format: ``user:<user_id>:<org_uuid>``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from ai_portal.notify.model import Notification


def _parse_recipient(recipient: str) -> tuple[int, uuid.UUID]:
    parts = recipient.split(":")
    if len(parts) != 3 or parts[0] != "user":
        raise ValueError(
            f"in_app recipient must be 'user:<id>:<org_uuid>', got: {recipient!r}"
        )
    try:
        user_id = int(parts[1])
        org_id = uuid.UUID(parts[2])
    except (ValueError, TypeError) as e:
        raise ValueError(f"in_app recipient malformed: {recipient!r}") from e
    return user_id, org_id


class InAppChannel:
    """Persist Notification row via injected session factory.

    ``session_factory`` returns an object exposing ``add()`` + ``commit()``
    (SQLAlchemy Session compatible). Caller manages lifecycle.
    """

    def __init__(self, session_factory: Callable[[], object]) -> None:
        self._session_factory = session_factory

    async def send(
        self,
        recipient: str,
        template_id: str,
        payload: dict,
    ) -> None:
        user_id, org_id = _parse_recipient(recipient)
        session = self._session_factory()
        row = Notification(
            org_id=org_id,
            user_id=user_id,
            channel="in_app",
            template_id=template_id,
            payload=payload,
        )
        session.add(row)
        session.commit()
