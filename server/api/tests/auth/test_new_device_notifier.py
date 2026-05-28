"""Bridge between auth.sessions hook and notify.send_event."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from ai_portal.auth import sessions as sess
from ai_portal.auth.new_device_notify import (
    NEW_DEVICE_EVENT_TYPE,
    NEW_DEVICE_TEMPLATE_ID,
    install_new_device_notifier,
)


class _CapturingNotify:
    """NotifyService stand-in: captures send_event calls."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_event(self, *, user_id, event_type, template_id, payload):
        self.events.append(
            {
                "user_id": user_id,
                "event_type": event_type,
                "template_id": template_id,
                "payload": payload,
            }
        )


@pytest.mark.asyncio
async def test_install_wires_send_event_with_expected_shape():
    notify = _CapturingNotify()
    install_new_device_notifier(notify)
    try:
        sess._new_device_hook(  # type: ignore[misc]
            42, "9.9.9.9", "Edge/120", datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
        )
        # Allow scheduled task to run.
        await asyncio.sleep(0)
        assert len(notify.events) == 1
        evt = notify.events[0]
        assert evt["user_id"] == 42
        assert evt["event_type"] == NEW_DEVICE_EVENT_TYPE
        assert evt["template_id"] == NEW_DEVICE_TEMPLATE_ID
        assert evt["payload"]["ip"] == "9.9.9.9"
        assert evt["payload"]["user_agent"] == "Edge/120"
        assert "2026-05-28" in evt["payload"]["ts"]
    finally:
        sess.set_new_device_hook(None)


def test_hook_outside_loop_drops_gracefully(caplog):
    notify = _CapturingNotify()
    install_new_device_notifier(notify)
    try:
        # No running event loop — must not raise.
        sess._new_device_hook(  # type: ignore[misc]
            7, "1.1.1.1", "ua", datetime.now(UTC)
        )
        assert notify.events == []
    finally:
        sess.set_new_device_hook(None)
