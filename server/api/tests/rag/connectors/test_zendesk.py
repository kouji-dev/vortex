"""zendesk connector — articles + opt-in tickets via a fake client."""

from __future__ import annotations

import pytest


class _FakeZendeskClient:
    async def list_articles(self):
        return [
            {
                "id": 11,
                "title": "Reset password",
                "body": "<p>steps</p>",
                "updated_at": "2026-05-01T00:00:00Z",
                "section_id": 100,
            }
        ]

    async def list_tickets(self):
        return [
            {
                "id": 99,
                "subject": "Cannot login",
                "description": "I cannot login",
                "updated_at": "2026-05-10T00:00:00Z",
                "submitter_id": 7,
                "assignee_id": 8,
            }
        ]


class _SecretStore:
    def __init__(self, client):
        self.zendesk_client = client


@pytest.mark.asyncio
async def test_zendesk_articles_only_by_default():
    from ai_portal.rag.connectors.adapters.zendesk import ZendeskConnector

    conn = await ZendeskConnector.setup(
        config={"subdomain": "acme"}, secret_store=_SecretStore(_FakeZendeskClient())
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    assert [d.source_uri for d in docs] == ["zendesk://articles/11"]


@pytest.mark.asyncio
async def test_zendesk_tickets_opt_in_acls():
    from ai_portal.rag.connectors.adapters.zendesk import ZendeskConnector

    conn = await ZendeskConnector.setup(
        config={"subdomain": "acme", "tickets_opt_in": True},
        secret_store=_SecretStore(_FakeZendeskClient()),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    uris = {d.source_uri for d in docs}
    assert "zendesk://articles/11" in uris
    assert "zendesk://tickets/99" in uris
    ticket = next(d for d in docs if d.source_uri == "zendesk://tickets/99")
    acl = await conn.acls(ticket)
    assert acl.user_ids == {"7", "8"}
    article = next(d for d in docs if d.source_uri == "zendesk://articles/11")
    article_acl = await conn.acls(article)
    assert article_acl.public is True
