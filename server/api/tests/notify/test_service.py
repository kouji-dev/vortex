"""NotifyService — fan-out to registered channels."""

from __future__ import annotations

import pytest

from ai_portal.notify.protocol import Channel
from ai_portal.notify.service import NotifyService


class _RecordingChannel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    async def send(self, recipient: str, template_id: str, payload: dict) -> None:
        self.calls.append((recipient, template_id, payload))


@pytest.mark.asyncio
async def test_service_dispatches_to_named_channel():
    in_app = _RecordingChannel()
    smtp = _RecordingChannel()
    svc = NotifyService(channels={"in_app": in_app, "smtp": smtp})

    await svc.send(
        channel="smtp",
        recipient="a@b.com",
        template_id="verify_email",
        payload={"verify_url": "https://x"},
    )

    assert smtp.calls == [("a@b.com", "verify_email", {"verify_url": "https://x"})]
    assert in_app.calls == []


@pytest.mark.asyncio
async def test_service_unknown_channel_raises():
    svc = NotifyService(channels={})
    with pytest.raises(KeyError):
        await svc.send(channel="missing", recipient="x", template_id="y", payload={})


def test_channel_protocol_runtime_checkable():
    # _RecordingChannel duck-types Channel
    chan: Channel = _RecordingChannel()  # type: ignore[assignment]
    assert hasattr(chan, "send")
