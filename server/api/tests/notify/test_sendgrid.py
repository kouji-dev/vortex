"""SendGrid channel — Jinja2 template + httpx POST to v3 mail/send, mocked via respx."""
from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.notify.channels.sendgrid import (
    SENDGRID_API_URL,
    SendgridChannel,
    SendgridConfig,
    SendgridSendFailed,
)


def _cfg(**overrides) -> SendgridConfig:
    base = {
        "api_key": "SG.test-key",
        "from_addr": "noreply@portal.test",
        "from_name": "Portal",
    }
    base.update(overrides)
    return SendgridConfig(**base)


@pytest.mark.asyncio
@respx.mock
async def test_send_posts_v3_mail_send_with_rendered_template():
    route = respx.post(SENDGRID_API_URL).respond(status_code=202)
    channel = SendgridChannel(_cfg())
    await channel.send(
        recipient="alice@acme.com",
        template_id="verify_email",
        payload={"verify_url": "https://portal.test/v?t=abc"},
    )
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer SG.test-key"
    assert sent.headers["content-type"].startswith("application/json")
    body = sent.content.decode("utf-8")
    assert "alice@acme.com" in body
    assert "noreply@portal.test" in body
    assert "https://portal.test/v?t=abc" in body


@pytest.mark.asyncio
@respx.mock
async def test_send_includes_from_name_when_configured():
    route = respx.post(SENDGRID_API_URL).respond(status_code=202)
    channel = SendgridChannel(_cfg(from_name="Portal HQ"))
    await channel.send(
        recipient="bob@acme.com",
        template_id="verify_email",
        payload={"verify_url": "https://portal.test/x"},
    )
    payload = route.calls.last.request.read().decode("utf-8")
    assert "Portal HQ" in payload


@pytest.mark.asyncio
@respx.mock
async def test_send_passes_sandbox_flag_when_enabled():
    route = respx.post(SENDGRID_API_URL).respond(status_code=202)
    channel = SendgridChannel(_cfg(sandbox=True))
    await channel.send(
        recipient="x@y.z",
        template_id="verify_email",
        payload={"verify_url": "https://portal.test/y"},
    )
    payload = route.calls.last.request.read().decode("utf-8")
    assert "sandbox_mode" in payload


@pytest.mark.asyncio
@respx.mock
async def test_send_raises_on_non_2xx():
    respx.post(SENDGRID_API_URL).respond(status_code=401, text="unauthorized")
    channel = SendgridChannel(_cfg())
    with pytest.raises(SendgridSendFailed) as ei:
        await channel.send(
            recipient="x@y.z",
            template_id="verify_email",
            payload={"verify_url": "https://portal.test/z"},
        )
    assert ei.value.status_code == 401


@pytest.mark.asyncio
@respx.mock
async def test_send_unknown_template_raises_keyerror():
    respx.post(SENDGRID_API_URL).respond(status_code=202)
    channel = SendgridChannel(_cfg())
    with pytest.raises(KeyError):
        await channel.send(
            recipient="x@y.z",
            template_id="does_not_exist",
            payload={},
        )


@pytest.mark.asyncio
@respx.mock
async def test_send_uses_custom_base_url():
    custom = "https://eu.sendgrid.example/v3/mail/send"
    route = respx.post(custom).respond(status_code=202)
    channel = SendgridChannel(_cfg(base_url=custom))
    await channel.send(
        recipient="x@y.z",
        template_id="verify_email",
        payload={"verify_url": "https://portal.test/r"},
    )
    assert route.called


@pytest.mark.asyncio
async def test_send_uses_injected_async_client_when_provided():
    """Injected httpx.AsyncClient is used in place of opening a per-send client."""
    transport = httpx.MockTransport(lambda req: httpx.Response(202))
    async with httpx.AsyncClient(transport=transport) as injected:
        channel = SendgridChannel(_cfg(), client=injected)
        await channel.send(
            recipient="x@y.z",
            template_id="verify_email",
            payload={"verify_url": "https://portal.test/i"},
        )


def test_channels_module_exports_sendgrid():
    from ai_portal.notify import channels

    assert "SendgridChannel" in channels.__all__
    assert "SendgridConfig" in channels.__all__
