"""MinIO BlobStore — self-hosted S3-compatible storage.

Thin wrapper over :class:`~ai_portal.storage.providers.s3.S3BlobStore` that
forces path-style addressing (``http://host/bucket/key``) since MinIO
deployments rarely set up DNS for virtual-host addressing.
"""

from __future__ import annotations

from ai_portal.storage.providers.s3 import S3BlobStore


class MinioBlobStore(S3BlobStore):
    """MinIO-flavoured S3BlobStore."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        super().__init__(
            bucket,
            region=region,
            endpoint_url=endpoint_url,
            access_key=access_key,
            secret_key=secret_key,
            signature_version="s3v4",
            addressing_style="path",
        )
