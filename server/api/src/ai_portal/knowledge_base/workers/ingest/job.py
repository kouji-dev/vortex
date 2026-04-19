"""RQ entrypoint — importable string target for ``rq.Queue.enqueue``."""
from __future__ import annotations

from ai_portal.knowledge_base.workers.ingest.worker import ingest_document_worker


def run_ingest_job(document_id: int) -> None:
    ingest_document_worker(document_id)
