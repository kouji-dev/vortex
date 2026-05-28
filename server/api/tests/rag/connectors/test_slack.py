"""slack connector — channels + threads + files via a fake client."""

from __future__ import annotations

import pytest


class _FakeSlackClient:
    def __init__(self) -> None:
        self._history = {
            "C1": [
                {
                    "ts": "1000.000001",
                    "text": "hello world",
                    "thread_ts": "1000.000001",
                    "reply_count": 2,
                    "files": [
                        {
                            "id": "F1",
                            "name": "spec.pdf",
                            "mimetype": "application/pdf",
                            "size": 12,
                        }
                    ],
                },
                {"ts": "2000.000001", "text": "another"},
            ]
        }
        self._replies = {
            ("C1", "1000.000001"): [
                {"ts": "1000.000001", "text": "hello world"},  # parent
                {"ts": "1100.000001", "text": "reply1"},
                {"ts": "1200.000001", "text": "reply2"},
            ]
        }
        self._members = {"C1": ["U1", "U2", "U3"]}

    async def history(self, channel_id):
        return list(self._history.get(channel_id, []))

    async def replies(self, channel_id, ts):
        msgs = list(self._replies.get((channel_id, ts), []))
        return msgs[1:]

    async def members(self, channel_id):
        return list(self._members.get(channel_id, []))


class _SecretStore:
    def __init__(self, client):
        self.slack_client = client


@pytest.mark.asyncio
async def test_slack_discover_messages_threads_files():
    from ai_portal.rag.connectors.adapters.slack import SlackConnector

    conn = await SlackConnector.setup(
        config={"channel_ids": ["C1"]},
        secret_store=_SecretStore(_FakeSlackClient()),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    uris = [d.source_uri for d in docs]
    assert "slack://C1/messages/1000.000001" in uris
    assert "slack://C1/messages/2000.000001" in uris
    assert "slack://C1/files/F1" in uris
    # Thread replies (not parent):
    assert "slack://C1/messages/1100.000001" in uris
    assert "slack://C1/messages/1200.000001" in uris

    msg_doc = next(
        d for d in docs if d.source_uri == "slack://C1/messages/1000.000001"
    )
    acl = await conn.acls(msg_doc)
    assert acl.user_ids == {"U1", "U2", "U3"}


@pytest.mark.asyncio
async def test_slack_delta_skips_older_ts():
    from ai_portal.rag.connectors.adapters.slack import SlackConnector

    conn = await SlackConnector.setup(
        config={"channel_ids": ["C1"], "include_threads": False, "include_files": False},
        secret_store=_SecretStore(_FakeSlackClient()),
    )
    docs = [sd async for sd in conn.discover(cursor="1500.000000")]
    assert [d.source_uri for d in docs] == ["slack://C1/messages/2000.000001"]
