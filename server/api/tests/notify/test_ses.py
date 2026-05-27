"""SES channel — renders template + dispatches via boto3 SES client (stubbed)."""

from __future__ import annotations

import pytest
from botocore.stub import ANY, Stubber

from ai_portal.notify.channels.ses import SesChannel, SesConfig


@pytest.mark.asyncio
async def test_ses_send_renders_template_and_calls_send_email():
    cfg = SesConfig(
        region="eu-west-1",
        from_addr="noreply@portal.test",
        access_key_id="AKIA",
        secret_access_key="SECRET",
    )
    channel = SesChannel(cfg)

    with Stubber(channel._client) as stub:
        stub.add_response(
            "send_email",
            expected_params={
                "Source": "noreply@portal.test",
                "Destination": {"ToAddresses": ["alice@acme.com"]},
                "Message": {
                    "Subject": {"Data": ANY, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": ANY, "Charset": "UTF-8"}},
                },
            },
            service_response={"MessageId": "fake-id"},
        )
        await channel.send(
            recipient="alice@acme.com",
            template_id="verify_email",
            payload={"verify_url": "https://portal.test/v?t=abc"},
        )
        stub.assert_no_pending_responses()


@pytest.mark.asyncio
async def test_ses_send_passes_rendered_body():
    cfg = SesConfig(
        region="eu-west-1",
        from_addr="noreply@portal.test",
        access_key_id="x",
        secret_access_key="y",
    )
    channel = SesChannel(cfg)

    captured: dict = {}
    real_send = channel._client.send_email

    def _fake_send_email(**kwargs):
        captured.update(kwargs)
        return {"MessageId": "fake"}

    channel._client.send_email = _fake_send_email  # type: ignore[method-assign]
    try:
        await channel.send(
            recipient="bob@acme.com",
            template_id="verify_email",
            payload={"verify_url": "https://portal.test/x"},
        )
    finally:
        channel._client.send_email = real_send  # type: ignore[method-assign]

    assert captured["Source"] == "noreply@portal.test"
    assert captured["Destination"]["ToAddresses"] == ["bob@acme.com"]
    body = captured["Message"]["Body"]["Text"]["Data"]
    assert "https://portal.test/x" in body


@pytest.mark.asyncio
async def test_ses_send_unknown_template_raises():
    cfg = SesConfig(
        region="eu-west-1",
        from_addr="noreply@portal.test",
        access_key_id="x",
        secret_access_key="y",
    )
    channel = SesChannel(cfg)

    with pytest.raises(KeyError):
        await channel.send(
            recipient="x@y.z",
            template_id="does_not_exist",
            payload={},
        )
