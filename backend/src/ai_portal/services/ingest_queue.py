"""RQ-backed ingest queue when ``REDIS_URL`` is configured."""
from __future__ import annotations

import logging

from ai_portal.config import Settings, get_settings

logger = logging.getLogger(__name__)

INGEST_QUEUE_NAME = "ingest"
INGEST_JOB_FUNC = "ai_portal.workers.ingest.job.run_ingest_job"


def ingest_uses_queue(settings: Settings | None = None) -> bool:
    st = settings or get_settings()
    return bool(st.redis_url.strip())


def enqueue_document_ingest(document_id: int, *, settings: Settings | None = None) -> None:
    """Push ``document_id`` onto the ingest queue. Raises if enqueue fails."""
    st = settings or get_settings()
    from redis import Redis
    from rq import Queue

    conn = Redis.from_url(st.redis_url)
    q = Queue(INGEST_QUEUE_NAME, connection=conn)
    q.enqueue(
        INGEST_JOB_FUNC,
        document_id,
        job_timeout="2h",
        result_ttl=0,
        failure_ttl=86_400,
    )
    logger.info("ingest_enqueued", extra={"document_id": document_id})
