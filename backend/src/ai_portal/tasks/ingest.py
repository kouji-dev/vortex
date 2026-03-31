# backend/src/ai_portal/tasks/ingest.py
"""Thin shim — delegates to workers/ingest/worker.py.

Kept for backward compatibility with any callers that import ingest_document
from this module. The actual implementation lives in the worker module so
it can be deployed and scaled independently.
"""
from __future__ import annotations

from ai_portal.workers.ingest.worker import ingest_document_worker


def ingest_document(document_id: int) -> str | None:
    """Backward-compatible entry point. Delegates to ingest_document_worker."""
    return ingest_document_worker(document_id)
