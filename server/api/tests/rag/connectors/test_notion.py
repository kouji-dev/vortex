"""notion connector — discover + fetch with a fake Notion client."""

from __future__ import annotations

import pytest


class _FakeNotionClient:
    def __init__(self) -> None:
        self._results = [
            {
                "id": "p1",
                "object": "page",
                "last_edited_time": "2026-05-01T00:00:00.000Z",
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [{"plain_text": "Plan"}],
                    }
                },
            },
            {
                "id": "p2",
                "object": "page",
                "last_edited_time": "2026-05-10T00:00:00.000Z",
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [{"plain_text": "Notes"}],
                    }
                },
            },
        ]
        self._blocks = {
            "p1": [
                {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "hello"}]}},
            ],
            "p2": [
                {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "title"}]}},
            ],
        }

    async def search(self, page_size):
        return list(self._results)

    async def get_page(self, page_id):
        return next(r for r in self._results if r["id"] == page_id)

    async def get_blocks(self, page_id):
        return list(self._blocks.get(page_id, []))


class _SecretStore:
    def __init__(self, client):
        self.notion_client = client


@pytest.mark.asyncio
async def test_notion_discover_and_fetch():
    from ai_portal.rag.connectors.adapters.notion import NotionConnector

    conn = await NotionConnector.setup(
        config={}, secret_store=_SecretStore(_FakeNotionClient())
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    assert {d.source_uri for d in docs} == {
        "notion://page/p1",
        "notion://page/p2",
    }
    assert next(d for d in docs if d.source_uri == "notion://page/p1").title == "Plan"
    fetched = await conn.fetch(docs[0])
    assert b"hello" in fetched.data or b"title" in fetched.data


@pytest.mark.asyncio
async def test_notion_delta_skips_older_pages():
    from ai_portal.rag.connectors.adapters.notion import NotionConnector

    conn = await NotionConnector.setup(
        config={}, secret_store=_SecretStore(_FakeNotionClient())
    )
    docs = [
        sd async for sd in conn.discover(cursor="2026-05-05T00:00:00.000Z")
    ]
    assert [d.source_uri for d in docs] == ["notion://page/p2"]
