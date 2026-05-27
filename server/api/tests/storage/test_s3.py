"""Tests for :class:`S3BlobStore` using ``moto`` to stub AWS S3."""

from __future__ import annotations

import os

import boto3
import pytest
from moto import mock_aws

from ai_portal.storage.protocol import BlobNotFound
from ai_portal.storage.providers.s3 import S3BlobStore

BUCKET = "test-bucket"
REGION = "us-east-1"


@pytest.fixture
def _aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # moto requires *some* credentials to be present in the environment.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def s3_store(_aws_env: None):  # type: ignore[no-untyped-def]
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(Bucket=BUCKET)
        yield S3BlobStore(BUCKET, region=REGION)


@pytest.mark.asyncio
async def test_put_returns_s3_url(s3_store: S3BlobStore) -> None:
    url = await s3_store.put("a/b.txt", b"hello", "text/plain")
    assert url == f"s3://{BUCKET}/a/b.txt"


@pytest.mark.asyncio
async def test_put_get_roundtrip(s3_store: S3BlobStore) -> None:
    await s3_store.put("k", b"\x00\x01\x02hello", "application/octet-stream")
    assert await s3_store.get("k") == b"\x00\x01\x02hello"


@pytest.mark.asyncio
async def test_get_missing_raises_blob_not_found(
    s3_store: S3BlobStore,
) -> None:
    with pytest.raises(BlobNotFound):
        await s3_store.get("missing")


@pytest.mark.asyncio
async def test_delete_idempotent(s3_store: S3BlobStore) -> None:
    await s3_store.delete("missing")  # no error
    await s3_store.put("k", b"v", "text/plain")
    await s3_store.delete("k")
    await s3_store.delete("k")  # second delete no-op
    with pytest.raises(BlobNotFound):
        await s3_store.get("k")


@pytest.mark.asyncio
async def test_presign_get_returns_url_with_signature(
    s3_store: S3BlobStore,
) -> None:
    await s3_store.put("k", b"v", "text/plain")
    url = await s3_store.presign_get("k", 600)
    assert url.startswith("http")
    assert "Signature=" in url or "X-Amz-Signature=" in url
    assert "k" in url


@pytest.mark.asyncio
async def test_presign_put_returns_url_for_upload(
    s3_store: S3BlobStore,
) -> None:
    url = await s3_store.presign_put("new-key", "image/png", 600)
    assert url.startswith("http")
    assert "new-key" in url


@pytest.mark.asyncio
async def test_content_type_persisted(s3_store: S3BlobStore) -> None:
    await s3_store.put("a.json", b"{}", "application/json")
    # Inspect via boto3 directly — confirm provider passed ContentType.
    resp = boto3.client("s3", region_name=REGION).head_object(
        Bucket=BUCKET, Key="a.json"
    )
    assert resp["ContentType"] == "application/json"


def test_default_aws_env_set(_aws_env: None) -> None:
    assert os.environ["AWS_ACCESS_KEY_ID"] == "testing"
