"""imap_email connector — discover + UID delta with a fake IMAP client."""

from __future__ import annotations

import pytest


class _FakeImapClient:
    def __init__(self) -> None:
        self._messages = {
            1: {"subject": "First", "body": "first body", "from": "a@x.test"},
            2: {
                "subject": "Second",
                "body": "second body",
                "from": "b@x.test",
                "attachments": [
                    {
                        "id": "a1",
                        "filename": "spec.pdf",
                        "content_type": "application/pdf",
                        "data": b"%PDF",
                    }
                ],
            },
            3: {"subject": "Third", "body": "third body"},
        }

    async def search(self, folder, label):
        return list(self._messages.keys())

    async def fetch_message(self, uid):
        return self._messages[uid]


class _SecretStore:
    def __init__(self, client):
        self.imap_client = client


@pytest.mark.asyncio
async def test_imap_discover_with_attachments():
    from ai_portal.rag.connectors.adapters.imap_email import ImapEmailConnector

    conn = await ImapEmailConnector.setup(
        config={"host": "x", "username": "u", "folder": "INBOX"},
        secret_store=_SecretStore(_FakeImapClient()),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    uris = {d.source_uri for d in docs}
    assert "imap://INBOX/1" in uris
    assert "imap://INBOX/2" in uris
    assert "imap://INBOX/2/att/a1" in uris
    assert await conn.delta_cursor() == "3"

    att = next(d for d in docs if d.source_uri.endswith("/att/a1"))
    fetched = await conn.fetch(att)
    assert fetched.data == b"%PDF"


@pytest.mark.asyncio
async def test_imap_delta_skips_old_uids():
    from ai_portal.rag.connectors.adapters.imap_email import ImapEmailConnector

    conn = await ImapEmailConnector.setup(
        config={"host": "x", "username": "u", "folder": "INBOX"},
        secret_store=_SecretStore(_FakeImapClient()),
    )
    docs = [sd async for sd in conn.discover(cursor="2")]
    assert [d.source_uri for d in docs if "/att/" not in d.source_uri] == [
        "imap://INBOX/3"
    ]
