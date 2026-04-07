# Re-export shim — real implementation moved to knowledge_base/service.py
from ai_portal.knowledge_base.service import (  # noqa: F401
    ingest_uses_queue,
    enqueue_document_ingest,
    INGEST_QUEUE_NAME,
    INGEST_JOB_FUNC,
)
