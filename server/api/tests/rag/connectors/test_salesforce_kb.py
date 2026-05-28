"""salesforce_kb connector — articles via a fake SOQL client."""

from __future__ import annotations

import pytest


class _FakeSfClient:
    async def query_articles(self, publish_status, language):
        return [
            {
                "Id": "ka1",
                "Title": "Reset password",
                "ArticleNumber": "000001",
                "Summary": "How to reset",
                "ArticleBody": "<p>steps</p>",
                "Language": "en_US",
                "LastModifiedDate": "2026-05-01T00:00:00.000+0000",
                "PublishStatus": "Online",
            },
            {
                "Id": "ka2",
                "Title": "Billing FAQ",
                "ArticleNumber": "000002",
                "Summary": "Billing",
                "ArticleBody": "<p>faq</p>",
                "Language": "en_US",
                "LastModifiedDate": "2026-05-10T00:00:00.000+0000",
                "PublishStatus": "Online",
            },
        ]


class _SecretStore:
    def __init__(self, client):
        self.salesforce_client = client


@pytest.mark.asyncio
async def test_sf_kb_discover_and_fetch():
    from ai_portal.rag.connectors.adapters.salesforce_kb import (
        SalesforceKbConnector,
    )

    conn = await SalesforceKbConnector.setup(
        config={}, secret_store=_SecretStore(_FakeSfClient())
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    assert {d.source_uri for d in docs} == {
        "salesforce://kb/ka1",
        "salesforce://kb/ka2",
    }
    fetched = await conn.fetch(docs[0])
    assert b"<p>steps</p>" in fetched.data or b"<p>faq</p>" in fetched.data


@pytest.mark.asyncio
async def test_sf_kb_delta_skips_old_articles():
    from ai_portal.rag.connectors.adapters.salesforce_kb import (
        SalesforceKbConnector,
    )

    conn = await SalesforceKbConnector.setup(
        config={}, secret_store=_SecretStore(_FakeSfClient())
    )
    docs = [
        sd
        async for sd in conn.discover(cursor="2026-05-05T00:00:00.000+0000")
    ]
    assert [d.source_uri for d in docs] == ["salesforce://kb/ka2"]
