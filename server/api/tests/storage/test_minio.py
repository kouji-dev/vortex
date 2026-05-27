"""Tests for :class:`MinioBlobStore`.

MinIO speaks S3 — moto stands in. The behavioural surface mirrors
``test_s3.py``; here we focus on the MinIO-specific config: explicit
``endpoint_url``, credentials, and **path-style** addressing.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from ai_portal.storage.protocol import BlobNotFound
from ai_portal.storage.providers.minio import MinioBlobStore
from ai_portal.storage.providers.s3 import S3BlobStore

BUCKET = "minio-bucket"
ENDPOINT = "http://localhost:9000"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"


@pytest.fixture
def minio_store(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    # moto only intercepts the canonical AWS endpoints by default; opt in to
    # custom endpoints so the MinIO ``endpoint_url`` is rerouted to the mock.
    monkeypatch.setenv("MOTO_S3_CUSTOM_ENDPOINTS", ENDPOINT)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", ACCESS_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SECRET_KEY)
    with mock_aws():
        boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name="us-east-1",
        ).create_bucket(Bucket=BUCKET)
        yield MinioBlobStore(
            BUCKET,
            endpoint_url=ENDPOINT,
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
        )


def test_minio_extends_s3_store() -> None:
    assert issubclass(MinioBlobStore, S3BlobStore)


def test_minio_uses_path_style_addressing() -> None:
    store = MinioBlobStore(
        BUCKET,
        endpoint_url=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
    )
    # Force path-style so URLs are http://host/bucket/key (DNS-friendly).
    config = store._client_kwargs["config"]
    assert config.s3["addressing_style"] == "path"


@pytest.mark.asyncio
async def test_put_get_roundtrip(minio_store: MinioBlobStore) -> None:
    url = await minio_store.put("dir/file.bin", b"\x01\x02", "image/png")
    assert url == f"s3://{BUCKET}/dir/file.bin"
    assert await minio_store.get("dir/file.bin") == b"\x01\x02"


@pytest.mark.asyncio
async def test_get_missing_raises(minio_store: MinioBlobStore) -> None:
    with pytest.raises(BlobNotFound):
        await minio_store.get("missing")


@pytest.mark.asyncio
async def test_delete_then_get(minio_store: MinioBlobStore) -> None:
    await minio_store.put("k", b"v", "text/plain")
    await minio_store.delete("k")
    with pytest.raises(BlobNotFound):
        await minio_store.get("k")


@pytest.mark.asyncio
async def test_presign_get_includes_bucket_path(
    minio_store: MinioBlobStore,
) -> None:
    await minio_store.put("k", b"v", "text/plain")
    url = await minio_store.presign_get("k", 60)
    # Path-style: bucket is in the URL path, not the host.
    assert f"/{BUCKET}/k" in url


@pytest.mark.asyncio
async def test_presign_put_includes_bucket_path(
    minio_store: MinioBlobStore,
) -> None:
    url = await minio_store.presign_put("k", "text/plain", 60)
    assert f"/{BUCKET}/k" in url
