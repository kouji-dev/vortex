"""Concrete connector adapters.

Importing this package triggers registration of all bundled connectors.
Downstream code should not import individual modules — use
``ai_portal.rag.connectors.get(name)`` to resolve.
"""

from __future__ import annotations

from ai_portal.rag.connectors.adapters import (  # noqa: F401
    azure_blob,
    confluence,
    file_upload,
    gcs_bucket,
    google_drive,
    notion,
    onedrive_sharepoint,
    s3_bucket,
    slack,
    web_crawler,
)
