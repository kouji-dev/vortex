"""SMTP channel — renders Jinja2 template + dispatches via mocked SMTP."""

from __future__ import annotations

from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from ai_portal.notify.channels.smtp import SmtpChannel, SmtpConfig


@pytest.mark.asyncio
async def test_smtp_send_renders_template_and_sends():
    cfg = SmtpConfig(
        host="smtp.test",
        port=587,
        username="bot",
        password="pw",
        from_addr="noreply@portal.test",
        use_tls=True,
    )
    channel = SmtpChannel(cfg)

    with patch("ai_portal.notify.channels.smtp.smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp

        await channel.send(
            recipient="alice@acme.com",
            template_id="verify_email",
            payload={"verify_url": "https://portal.test/verify?t=abc"},
        )

        smtp_cls.assert_called_once_with("smtp.test", 587)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("bot", "pw")
        smtp.send_message.assert_called_once()
        msg: EmailMessage = smtp.send_message.call_args.args[0]
        assert msg["To"] == "alice@acme.com"
        assert msg["From"] == "noreply@portal.test"
        body = msg.get_content()
        assert "https://portal.test/verify?t=abc" in body


@pytest.mark.asyncio
async def test_smtp_send_skips_tls_when_disabled():
    cfg = SmtpConfig(
        host="smtp.test",
        port=25,
        username=None,
        password=None,
        from_addr="noreply@portal.test",
        use_tls=False,
    )
    channel = SmtpChannel(cfg)

    with patch("ai_portal.notify.channels.smtp.smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp

        await channel.send(
            recipient="bob@acme.com",
            template_id="verify_email",
            payload={"verify_url": "https://x"},
        )

        smtp.starttls.assert_not_called()
        smtp.login.assert_not_called()
        smtp.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_smtp_send_unknown_template_raises():
    cfg = SmtpConfig(
        host="smtp.test",
        port=25,
        username=None,
        password=None,
        from_addr="noreply@portal.test",
        use_tls=False,
    )
    channel = SmtpChannel(cfg)

    with patch("ai_portal.notify.channels.smtp.smtplib.SMTP"):
        with pytest.raises(KeyError):
            await channel.send(
                recipient="x@y.z",
                template_id="does_not_exist",
                payload={},
            )
