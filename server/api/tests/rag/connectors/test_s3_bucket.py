"""s3_bucket connector — discovery + fetch through a fake BlobStore."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


class _FakeS3Store:
    def __init__(self, entries):
        self._entries = entries

    async def list(self, prefix: str):
        return [e for e in self._entries if e["key"].startswith(prefix)]

    async def get(self, key: str) -> bytes:
        return f"s3-bytes:{key}".encode()


class _SecretStore:
    def __init__(self, store):
        self._store = store

    def build_s3_store(self, config):
        return self._store


@pytest.mark.asyncio
async def test_s3_discover_yields_qualified_uri_and_etag_token():
    from ai_portal.rag.connectors.adapters.s3_bucket import S3BucketConnector

    store = _FakeS3Store(
        [
            {
                "key": "docs/a.pdf",
                "size": 7,
                "modified_at": datetime(2026, 5, 1, tzinfo=UTC),
                "etag": "abc",
                "content_type": "application/pdf",
            },
        ]
    )
    conn = await S3BucketConnector.setup(
        config={"bucket": "acme", "prefix": "docs/"},
        secret_store=_SecretStore(store),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    assert docs[0].source_uri == "s3://acme/docs/a.pdf"
    assert docs[0].cursor_token == "abc"
    fetched = await conn.fetch(docs[0])
    assert fetched.data == b"s3-bytes:docs/a.pdf"
    assert fetched.meta["bucket"] == "acme"
