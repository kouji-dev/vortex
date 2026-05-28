"""Gateway Files API — proxy for Anthropic Files + OpenAI Assistants compat.

Files are stored in the Control Plane :class:`BlobStore`; one row in
``gateway_files`` tracks each upload (key, content type, size, purpose,
owner). Downloads go through short-lived presigned URLs.
"""

from __future__ import annotations

from ai_portal.gateway.files.model import GatewayFile
from ai_portal.gateway.files.router import router
from ai_portal.gateway.files.service import (
    FileMetadata,
    FileNotFound,
    FilesService,
)

__all__ = [
    "FileMetadata",
    "FileNotFound",
    "FilesService",
    "GatewayFile",
    "router",
]
