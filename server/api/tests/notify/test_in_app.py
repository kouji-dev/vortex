"""In-app channel — writes Notification rows; no external IO."""

from __future__ import annotations

import uuid

import pytest

from ai_portal.notify.channels.in_app import InAppChannel
from ai_portal.notify.model import Notification


class _StubSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_in_app_send_writes_notification_row():
    session = _StubSession()
    channel = InAppChannel(session_factory=lambda: session)
    user_id = 42
    org_id = uuid.uuid4()

    await channel.send(
        recipient=f"user:{user_id}:{org_id}",
        template_id="org_invitation",
        payload={"org_name": "Acme", "invite_url": "https://x/y"},
    )

    assert len(session.added) == 1
    n = session.added[0]
    assert isinstance(n, Notification)
    assert n.user_id == user_id
    assert n.org_id == org_id
    assert n.template_id == "org_invitation"
    assert n.channel == "in_app"
    assert n.payload == {"org_name": "Acme", "invite_url": "https://x/y"}
    assert session.committed is True


@pytest.mark.asyncio
async def test_in_app_send_rejects_bad_recipient_format():
    session = _StubSession()
    channel = InAppChannel(session_factory=lambda: session)

    with pytest.raises(ValueError):
        await channel.send(
            recipient="not-a-valid-user-recipient",
            template_id="x",
            payload={},
        )
