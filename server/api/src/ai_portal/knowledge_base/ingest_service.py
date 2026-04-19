from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, UploadFile

from ai_portal.core.config import Settings, get_settings
from ai_portal.knowledge_base.model import KnowledgeBase
from ai_portal.rag.providers import voyage as embedding_svc
from ai_portal.knowledge_base.workers.ingest.worker import ingest_document_worker
from ai_portal.knowledge_base import repository as repo
from ai_portal.knowledge_base.schemas import DocumentUploadResultRead

logger = logging.getLogger(__name__)

INGEST_QUEUE_NAME = "ingest"
INGEST_JOB_FUNC = "ai_portal.knowledge_base.workers.ingest.job.run_ingest_job"


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


def _schedule_document_ingest(document_id: int, background_tasks: BackgroundTasks) -> None:
    """Run ingest asynchronously: RQ worker when Redis is configured, else FastAPI background task."""
    settings = get_settings()
    if ingest_uses_queue(settings):
        try:
            enqueue_document_ingest(document_id, settings=settings)
            return
        except Exception:
            logger.exception(
                "ingest_enqueue_failed_falling_back_to_background",
                extra={"document_id": document_id},
            )
    background_tasks.add_task(ingest_document_worker, document_id)


async def store_and_queue_kb_upload(
    kb: KnowledgeBase,
    upload: UploadFile,
    db,
    settings,
    background_tasks: BackgroundTasks,
) -> DocumentUploadResultRead:
    safe_name = Path(upload.filename or "upload").name
    content = await upload.read()
    max_bytes = settings.kb_max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        return DocumentUploadResultRead(
            status="failed",
            filename=safe_name,
            ingest_error=(
                f"File too large. Maximum size is {settings.kb_max_file_size_mb} MB."
            ),
        )

    dest_dir = Path(settings.upload_dir) / "kb" / str(kb.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest_path = dest_dir / dest_name
    dest_path.write_bytes(content)

    doc = repo.create_document(db, kb.id, safe_name, str(dest_path.resolve()))

    if not embedding_svc.embeddings_configured(settings):
        doc = repo.update_document_status(db, doc, "failed")
        return DocumentUploadResultRead(
            document_id=doc.id,
            status=doc.status,
            filename=safe_name,
            ingest_error=embedding_svc.embeddings_missing_key_message(),
        )

    _schedule_document_ingest(doc.id, background_tasks)
    db.refresh(doc)
    return DocumentUploadResultRead(
        document_id=doc.id,
        status=doc.status,
        filename=safe_name,
    )
