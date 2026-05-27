"""Slack webhook channel — renders + posts to a Slack incoming webhook URL."""

from __future__ import annotations

import json

import httpx
import pytest

from ai_portal.notify.channels.slack_webhook import SlackWebhookChannel


def _mock_transport(captured: dict, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(status, text="ok")

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_slack_send_posts_to_webhook_url():
    captured: dict = {}
    channel = SlackWebhookChannel(transport=_mock_transport(captured))

    await channel.send(
        recipient="https://hooks.slack.com/services/T/B/XYZ",
        template_id="org_invitation",
        payload={"org_name": "Acme", "invite_url": "https://x/y"},
    )

    assert captured["url"] == "https://hooks.slack.com/services/T/B/XYZ"
    assert "text" in captured["body"]
    text = captured["body"]["text"]
    assert "Acme" in text or "https://x/y" in text


@pytest.mark.asyncio
async def test_slack_send_raises_on_http_error():
    captured: dict = {}
    channel = SlackWebhookChannel(transport=_mock_transport(captured, status=500))

    with pytest.raises(httpx.HTTPStatusError):
        await channel.send(
            recipient="https://hooks.slack.com/services/T/B/XYZ",
            template_id="org_invitation",
            payload={"org_name": "X", "invite_url": "https://x"},
        )


@pytest.mark.asyncio
async def test_slack_send_rejects_non_webhook_url():
    channel = SlackWebhookChannel(transport=_mock_transport({}))

    with pytest.raises(ValueError):
        await channel.send(
            recipient="not-a-url",
            template_id="org_invitation",
            payload={"org_name": "X", "invite_url": "https://x"},
        )


@pytest.mark.asyncio
async def test_slack_send_unknown_template_raises():
    channel = SlackWebhookChannel(transport=_mock_transport({}))

    with pytest.raises(KeyError):
        await channel.send(
            recipient="https://hooks.slack.com/services/A/B/C",
            template_id="does_not_exist",
            payload={},
        )
