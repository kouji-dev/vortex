"""User preference matrix — send_event() fans out by per-(user,event,channel) prefs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_portal.notify.prefs import EventPolicy, PrefMatrix
from ai_portal.notify.service import NotifyService


class _RecordingChannel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    async def send(self, recipient: str, template_id: str, payload: dict) -> None:
        self.calls.append((recipient, template_id, payload))


@pytest.mark.asyncio
async def test_send_event_fans_out_to_enabled_channels():
    smtp = _RecordingChannel()
    slack = _RecordingChannel()
    in_app = _RecordingChannel()
    svc = NotifyService(
        channels={"smtp": smtp, "slack_webhook": slack, "in_app": in_app}
    )

    matrix = PrefMatrix(
        prefs={
            (7, "budget.exceeded", "smtp"): True,
            (7, "budget.exceeded", "slack_webhook"): True,
            (7, "budget.exceeded", "in_app"): False,
        },
        recipients={
            "smtp": "alice@acme.com",
            "slack_webhook": "https://hooks.slack.com/services/A/B/C",
            "in_app": "user:7:00000000-0000-0000-0000-000000000001",
        },
    )
    svc.attach_prefs(matrix)

    await svc.send_event(
        user_id=7,
        event_type="budget.exceeded",
        template_id="verify_email",
        payload={"verify_url": "https://x/y"},
    )

    assert len(smtp.calls) == 1
    assert smtp.calls[0][0] == "alice@acme.com"
    assert len(slack.calls) == 1
    assert slack.calls[0][0] == "https://hooks.slack.com/services/A/B/C"
    assert in_app.calls == []


@pytest.mark.asyncio
async def test_send_event_respects_default_when_no_pref_row():
    smtp = _RecordingChannel()
    svc = NotifyService(channels={"smtp": smtp})

    matrix = PrefMatrix(
        prefs={},
        recipients={"smtp": "alice@acme.com"},
        defaults={"budget.exceeded": {"smtp": True}},
    )
    svc.attach_prefs(matrix)

    await svc.send_event(
        user_id=7,
        event_type="budget.exceeded",
        template_id="verify_email",
        payload={"verify_url": "https://x"},
    )
    assert len(smtp.calls) == 1


@pytest.mark.asyncio
async def test_send_event_user_opt_out_overrides_default():
    smtp = _RecordingChannel()
    svc = NotifyService(channels={"smtp": smtp})

    matrix = PrefMatrix(
        prefs={(7, "budget.exceeded", "smtp"): False},
        recipients={"smtp": "alice@acme.com"},
        defaults={"budget.exceeded": {"smtp": True}},
    )
    svc.attach_prefs(matrix)

    await svc.send_event(
        user_id=7,
        event_type="budget.exceeded",
        template_id="verify_email",
        payload={"verify_url": "https://x"},
    )
    assert smtp.calls == []


@pytest.mark.asyncio
async def test_send_event_throttles_within_window_drop_mode():
    smtp = _RecordingChannel()
    svc = NotifyService(channels={"smtp": smtp})

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def clock():
        return clock.t  # type: ignore[attr-defined]

    clock.t = now  # type: ignore[attr-defined]

    matrix = PrefMatrix(
        prefs={(7, "budget.warn", "smtp"): True},
        recipients={"smtp": "alice@acme.com"},
        policies={
            "budget.warn": EventPolicy(
                throttle_window=timedelta(minutes=5),
                mode="drop",
            )
        },
        clock=clock,
    )
    svc.attach_prefs(matrix)

    await svc.send_event(
        user_id=7,
        event_type="budget.warn",
        template_id="verify_email",
        payload={"verify_url": "https://a"},
    )
    clock.t = now + timedelta(minutes=1)  # type: ignore[attr-defined]
    await svc.send_event(
        user_id=7,
        event_type="budget.warn",
        template_id="verify_email",
        payload={"verify_url": "https://b"},
    )
    clock.t = now + timedelta(minutes=6)  # type: ignore[attr-defined]
    await svc.send_event(
        user_id=7,
        event_type="budget.warn",
        template_id="verify_email",
        payload={"verify_url": "https://c"},
    )

    assert len(smtp.calls) == 2
    assert smtp.calls[0][2]["verify_url"] == "https://a"
    assert smtp.calls[1][2]["verify_url"] == "https://c"


@pytest.mark.asyncio
async def test_send_event_digests_within_window_then_flushes():
    smtp = _RecordingChannel()
    svc = NotifyService(channels={"smtp": smtp})

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def clock():
        return clock.t  # type: ignore[attr-defined]

    clock.t = now  # type: ignore[attr-defined]

    matrix = PrefMatrix(
        prefs={(7, "kb.ingest.complete", "smtp"): True},
        recipients={"smtp": "alice@acme.com"},
        policies={
            "kb.ingest.complete": EventPolicy(
                throttle_window=timedelta(minutes=10),
                mode="digest",
            )
        },
        clock=clock,
    )
    svc.attach_prefs(matrix)

    await svc.send_event(
        user_id=7,
        event_type="kb.ingest.complete",
        template_id="verify_email",
        payload={"verify_url": "https://1"},
    )
    clock.t = now + timedelta(minutes=2)  # type: ignore[attr-defined]
    await svc.send_event(
        user_id=7,
        event_type="kb.ingest.complete",
        template_id="verify_email",
        payload={"verify_url": "https://2"},
    )
    clock.t = now + timedelta(minutes=4)  # type: ignore[attr-defined]
    await svc.send_event(
        user_id=7,
        event_type="kb.ingest.complete",
        template_id="verify_email",
        payload={"verify_url": "https://3"},
    )
    # first immediate; events 2+3 held for digest
    assert len(smtp.calls) == 1
    assert smtp.calls[0][2]["verify_url"] == "https://1"

    # advance past window and flush
    clock.t = now + timedelta(minutes=11)  # type: ignore[attr-defined]
    await svc.flush_digests()

    assert len(smtp.calls) == 2
    digest_payload = smtp.calls[1][2]
    assert digest_payload.get("digest_count") == 2
    assert digest_payload.get("events") == [
        {"verify_url": "https://2"},
        {"verify_url": "https://3"},
    ]


@pytest.mark.asyncio
async def test_send_event_silent_when_no_recipient_for_channel():
    smtp = _RecordingChannel()
    slack = _RecordingChannel()
    svc = NotifyService(channels={"smtp": smtp, "slack_webhook": slack})

    matrix = PrefMatrix(
        prefs={
            (7, "budget.exceeded", "smtp"): True,
            (7, "budget.exceeded", "slack_webhook"): True,
        },
        recipients={"smtp": "alice@acme.com"},  # no slack recipient
    )
    svc.attach_prefs(matrix)

    await svc.send_event(
        user_id=7,
        event_type="budget.exceeded",
        template_id="verify_email",
        payload={"verify_url": "https://x"},
    )

    assert len(smtp.calls) == 1
    assert slack.calls == []
