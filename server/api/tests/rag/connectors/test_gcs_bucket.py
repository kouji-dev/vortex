"""gcs_bucket connector — discovery using GCS generation as cursor."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


class _FakeGcsStore:
    def __init__(self, entries):
        self._entries = entries

    async def list(self, prefix: str):
        return [e for e in self._entries if e["key"].startswith(prefix)]

    async def get(self, key: str) -> bytes:
        return f"gs:{key}".encode()


class _SecretStore:
    def __init__(self, store):
        self._store = store

    def build_gcs_store(self, config):
        return self._store


@pytest.mark.asyncio
async def test_gcs_uses_generation_as_cursor():
    from ai_portal.rag.connectors.adapters.gcs_bucket import GcsBucketConnector

    store = _FakeGcsStore(
        [
            {
                "key": "p/a.txt",
                "generation": 100,
                "modified_at": datetime(2026, 5, 1, tzinfo=UTC),
            },
            {
                "key": "p/b.txt",
                "generation": 200,
                "modified_at": datetime(2026, 6, 1, tzinfo=UTC),
            },
        ]
    )
    conn = await GcsBucketConnector.setup(
        config={"bucket": "acme", "prefix": "p/"},
        secret_store=_SecretStore(store),
    )
    docs = [sd async for sd in conn.discover(cursor="100")]
    assert [d.source_uri for d in docs] == ["gs://acme/p/b.txt"]
    assert docs[0].cursor_token == "200"
