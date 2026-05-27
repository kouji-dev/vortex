"""Google Cloud Storage BlobStore.

Uses ``google-cloud-storage`` synchronously, dispatched via
``asyncio.to_thread``. Presigned URLs use v4 signing.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud import storage  # type: ignore[attr-defined]

from ai_portal.storage.protocol import BlobNotFound


class GcsBlobStore:
    """GCS-backed BlobStore."""

    def __init__(
        self,
        bucket: str,
        *,
        project: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.bucket_name = bucket
        self._project = project
        self._client = client

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is not None:
            return self._client
        if self._project is not None:
            return storage.Client(project=self._project)
        return storage.Client()

    def _blob(self, key: str):  # type: ignore[no-untyped-def]
        return self._get_client().bucket(self.bucket_name).blob(key)

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        def _put() -> str:
            blob = self._blob(key)
            blob.upload_from_string(data, content_type=content_type)
            return f"gs://{self.bucket_name}/{key}"

        return await asyncio.to_thread(_put)

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            try:
                return self._blob(key).download_as_bytes()
            except NotFound as exc:
                raise BlobNotFound(key) from exc

        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            try:
                self._blob(key).delete()
            except NotFound:
                return

        await asyncio.to_thread(_delete)

    async def presign_get(self, key: str, expires_in: int) -> str:
        def _sign() -> str:
            return self._blob(key).generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expires_in),
                method="GET",
            )

        return await asyncio.to_thread(_sign)

    async def presign_put(
        self, key: str, content_type: str, expires_in: int
    ) -> str:
        def _sign() -> str:
            return self._blob(key).generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expires_in),
                method="PUT",
                content_type=content_type,
            )

        return await asyncio.to_thread(_sign)
