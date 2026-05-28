"""Test the notify bootstrap helper and new-device wiring.

File-scoped: pure unit tests. No DB, no app lifespan.
"""

from __future__ import annotations

import os
import types
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from ai_portal.notify.bootstrap import build_notify_service


def _settings(**overrides):
    base = {"smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_password": ""}
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_build_returns_none_when_no_transport(monkeypatch):
    monkeypatch.delenv("SENDGRID_API_KEY", raising=False)
    monkeypatch.delenv("SENDGRID_FROM", raising=False)
    assert build_notify_service(_settings()) is None


def test_build_with_smtp_only(monkeypatch):
    monkeypatch.delenv("SENDGRID_API_KEY", raising=False)
    svc = build_notify_service(_settings(smtp_host="smtp.example.com"))
    assert svc is not None
    assert svc.has("email")


def test_build_with_sendgrid_only(monkeypatch):
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.xxx")
    monkeypatch.setenv("SENDGRID_FROM", "no-reply@example.com")
    svc = build_notify_service(_settings())
    assert svc is not None
    assert svc.has("email")


def test_install_new_device_notifier_calls_send_event():
    from ai_portal.auth import new_device_notify, sessions
    from ai_portal.notify.service import NotifyService

    notify = NotifyService(channels={})
    notify.send_event = AsyncMock()  # type: ignore[method-assign]

    new_device_notify.install_new_device_notifier(notify)
    try:
        # The hook is installed; calling it directly should schedule send_event.
        # We must run under an event loop so create_task works.
        import asyncio

        async def _drive():
            sessions._new_device_hook(  # type: ignore[attr-defined]
                42, "1.2.3.4", "ua/1.0", datetime.now(UTC)
            )
            # Yield control so the scheduled task runs.
            await asyncio.sleep(0)

        asyncio.run(_drive())
        notify.send_event.assert_awaited_once()
        kwargs = notify.send_event.await_args.kwargs
        assert kwargs["user_id"] == 42
        assert kwargs["event_type"] == "auth.login.new_device"
        assert kwargs["template_id"] == "auth_login_new_device"
        assert kwargs["payload"]["ip"] == "1.2.3.4"
    finally:
        sessions.set_new_device_hook(None)


def test_install_new_device_notifier_no_loop_drops_event(caplog):
    """When no loop is running, the hook must log + drop, not crash."""
    from ai_portal.auth import new_device_notify, sessions
    from ai_portal.notify.service import NotifyService

    notify = NotifyService(channels={})
    notify.send_event = AsyncMock()  # type: ignore[method-assign]

    new_device_notify.install_new_device_notifier(notify)
    try:
        sessions._new_device_hook(  # type: ignore[attr-defined]
            7, None, None, datetime.now(UTC)
        )
        notify.send_event.assert_not_awaited()
    finally:
        sessions.set_new_device_hook(None)


def test_lifespan_installs_new_device_notifier(monkeypatch):
    """When notify is configured, the lifespan installs the hook."""
    import asyncio

    from ai_portal.auth import sessions

    monkeypatch.setenv("SENDGRID_API_KEY", "SG.xxx")
    monkeypatch.setenv("SENDGRID_FROM", "no-reply@example.com")

    from ai_portal.main import app, lifespan  # noqa: PLC0415

    # Reset hook to default first so we can detect replacement.
    sessions.set_new_device_hook(None)
    default = sessions._new_device_hook  # type: ignore[attr-defined]

    async def _run():
        async with lifespan(app):
            assert sessions._new_device_hook is not default  # type: ignore[attr-defined]

    try:
        asyncio.run(_run())
    finally:
        sessions.set_new_device_hook(None)


def test_lifespan_skips_when_notify_not_configured(monkeypatch):
    """When no transport configured, lifespan must skip cleanly."""
    import asyncio

    from ai_portal.auth import sessions

    monkeypatch.delenv("SENDGRID_API_KEY", raising=False)
    monkeypatch.delenv("SENDGRID_FROM", raising=False)
    # Force smtp empty by clearing the cached settings.
    monkeypatch.setenv("SMTP_HOST", "")

    from ai_portal.main import app, lifespan  # noqa: PLC0415
    # Force the settings used during lifespan to report no SMTP host even if
    # the cached singleton has one. We monkeypatch the bootstrap module to
    # ignore SMTP from settings unconditionally.
    import ai_portal.notify.bootstrap as _bs  # noqa: PLC0415

    monkeypatch.setattr(_bs, "_maybe_smtp_channel", lambda _s: None)

    sessions.set_new_device_hook(None)
    default = sessions._new_device_hook  # type: ignore[attr-defined]

    async def _run():
        async with lifespan(app):
            # Hook left at default — no replacement happened.
            assert sessions._new_device_hook is default  # type: ignore[attr-defined]

    try:
        asyncio.run(_run())
    finally:
        sessions.set_new_device_hook(None)
