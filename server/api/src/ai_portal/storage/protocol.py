"""BlobStore protocol — uniform surface across all object-storage providers.

Implementations:
- ``providers.s3.S3BlobStore``         — AWS S3
- ``providers.minio.MinioBlobStore``   — self-hosted S3-compatible
- ``providers.azure_blob.AzureBlobStore`` — Azure Blob Storage
- ``providers.gcs.GcsBlobStore``       — Google Cloud Storage
- ``providers.local_fs.LocalFsBlobStore`` — dev / tests only

All methods are async even when the underlying SDK is sync — providers run
blocking work in a thread to keep the FastAPI event loop free.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class BlobNotFound(KeyError):
    """Raised when ``get`` or ``delete`` targets a missing key."""


@runtime_checkable
class BlobStore(Protocol):
    """Uniform contract for object storage providers.

    ``put``        — store bytes, return the canonical URL/URI of the object.
    ``get``        — fetch bytes by key. Raises :class:`BlobNotFound`.
    ``delete``     — remove by key. Idempotent (missing key = no-op).
    ``presign_get` — short-lived URL for direct download.
    ``presign_put` — short-lived URL for direct upload.

    Keys are opaque strings (path-like, slash-separated allowed). The
    provider is responsible for prefixing with its bucket/container.
    """

    async def put(self, key: str, data: bytes, content_type: str) -> str: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def presign_get(self, key: str, expires_in: int) -> str: ...

    async def presign_put(
        self, key: str, content_type: str, expires_in: int
    ) -> str: ...
