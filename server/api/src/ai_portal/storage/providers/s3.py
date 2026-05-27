"""AWS S3 BlobStore.

Uses ``boto3`` synchronously, dispatched to a thread via ``asyncio.to_thread``
so the event loop stays free. Suitable for any S3-compatible endpoint when
``endpoint_url`` is not provided; for self-hosted MinIO use
:mod:`ai_portal.storage.providers.minio` which forces path-style URLs.
"""

from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from ai_portal.storage.protocol import BlobNotFound


class S3BlobStore:
    """S3-backed BlobStore."""

    def __init__(
        self,
        bucket: str,
        *,
        region: str | None = None,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        signature_version: str = "s3v4",
        addressing_style: str = "virtual",
    ) -> None:
        self.bucket = bucket
        self._client_kwargs: dict[str, Any] = {
            "service_name": "s3",
            "config": Config(
                signature_version=signature_version,
                s3={"addressing_style": addressing_style},
            ),
        }
        if region is not None:
            self._client_kwargs["region_name"] = region
        if endpoint_url is not None:
            self._client_kwargs["endpoint_url"] = endpoint_url
        if access_key is not None:
            self._client_kwargs["aws_access_key_id"] = access_key
        if secret_key is not None:
            self._client_kwargs["aws_secret_access_key"] = secret_key

    def _client(self):  # type: ignore[no-untyped-def]
        # New client per call: boto3 clients are thread-safe but cheap; keeps
        # moto fixture lifecycles simple.
        return boto3.client(**self._client_kwargs)

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        def _put() -> str:
            self._client().put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            return f"s3://{self.bucket}/{key}"

        return await asyncio.to_thread(_put)

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            try:
                resp = self._client().get_object(Bucket=self.bucket, Key=key)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code in {"NoSuchKey", "404"}:
                    raise BlobNotFound(key) from exc
                raise
            return resp["Body"].read()

        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            self._client().delete_object(Bucket=self.bucket, Key=key)

        await asyncio.to_thread(_delete)

    async def presign_get(self, key: str, expires_in: int) -> str:
        def _sign() -> str:
            return self._client().generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )

        return await asyncio.to_thread(_sign)

    async def presign_put(
        self, key: str, content_type: str, expires_in: int
    ) -> str:
        def _sign() -> str:
            return self._client().generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )

        return await asyncio.to_thread(_sign)
