"""azure_blob connector — discovery + fetch through a fake BlobStore."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


class _FakeAzStore:
    def __init__(self, entries):
        self._entries = entries

    async def list(self, prefix: str):
        return [e for e in self._entries if e["key"].startswith(prefix)]

    async def get(self, key: str) -> bytes:
        return f"az:{key}".encode()


class _SecretStore:
    def __init__(self, store):
        self._store = store

    def build_azure_store(self, config):
        return self._store


@pytest.mark.asyncio
async def test_azure_discover_yields_qualified_uri():
    from ai_portal.rag.connectors.adapters.azure_blob import AzureBlobConnector

    store = _FakeAzStore(
        [
            {
                "key": "docs/a.docx",
                "size": 11,
                "modified_at": datetime(2026, 5, 1, tzinfo=UTC),
                "etag": "0x8D",
            }
        ]
    )
    conn = await AzureBlobConnector.setup(
        config={
            "account": "myacct",
            "container": "kb",
            "prefix": "docs/",
        },
        secret_store=_SecretStore(store),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    assert docs[0].source_uri == "azure://myacct/kb/docs/a.docx"
    fetched = await conn.fetch(docs[0])
    assert fetched.data == b"az:docs/a.docx"
    assert fetched.meta["container"] == "kb"
