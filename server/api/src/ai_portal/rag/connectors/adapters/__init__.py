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
    github,
    gitlab,
    google_drive,
    http_generic,
    imap_email,
    jira,
    notion,
    onedrive_sharepoint,
    s3_bucket,
    salesforce_kb,
    slack,
    web_crawler,
    zendesk,
)
