"""Object storage abstraction (BlobStore) for the Control Plane.

Bundled providers live under ``ai_portal.storage.providers``. The
:class:`BlobStore` protocol is the only stable surface — services depend on
the protocol, not the concrete provider.

Use :func:`build_blob_store` to instantiate a provider by name. Cross-cutting
modules (gdpr export worker, audit s3 sink, ...) call it via the control-plane
facade (``from ai_portal.control_plane import build_blob_store``).
"""

from __future__ import annotations

from typing import Any

from ai_portal.storage.protocol import BlobNotFound, BlobStore


def build_blob_store(kind: str, /, **config: Any) -> BlobStore:
    """Construct a :class:`BlobStore` provider by name.

    Supported kinds:

    - ``local_fs``    — keyword ``root`` (path). Dev/tests only.
    - ``s3``          — boto3 kwargs (``bucket``, ``region``, ...).
    - ``minio``       — S3-compatible kwargs + ``endpoint_url``.
    - ``azure_blob``  — Azure Blob kwargs (``container``, ``connection_string``).
    - ``gcs``         — GCS kwargs (``bucket``, ``credentials_path``).

    Raises :class:`ValueError` for unknown kinds.
    """
    if kind == "local_fs":
        from ai_portal.storage.providers.local_fs import LocalFsBlobStore  # noqa: PLC0415

        return LocalFsBlobStore(**config)
    if kind == "s3":
        from ai_portal.storage.providers.s3 import S3BlobStore  # noqa: PLC0415

        return S3BlobStore(**config)
    if kind == "minio":
        from ai_portal.storage.providers.minio import MinioBlobStore  # noqa: PLC0415

        return MinioBlobStore(**config)
    if kind == "azure_blob":
        from ai_portal.storage.providers.azure_blob import AzureBlobStore  # noqa: PLC0415

        return AzureBlobStore(**config)
    if kind == "gcs":
        from ai_portal.storage.providers.gcs import GcsBlobStore  # noqa: PLC0415

        return GcsBlobStore(**config)
    raise ValueError(f"unknown BlobStore kind: {kind!r}")


__all__ = ["BlobNotFound", "BlobStore", "build_blob_store"]
