# Re-export shim — real implementation moved to knowledge_base/workers/ingest/worker.py
from ai_portal.knowledge_base.workers.ingest.worker import *  # noqa: F401, F403
from ai_portal.knowledge_base.workers.ingest.worker import (  # noqa: F401
    _mark_document_ready,
    _persist_document_failure,
)
