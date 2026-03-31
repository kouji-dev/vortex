"""Ingest worker — decoupled from API layer."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models.document import Document, DocumentChunk
from ai_portal.services import embedding as embedding_svc
from ai_portal.workers.ingest.chunking import file_type_for_suffix, semantic_chunks
from ai_portal.workers.ingest.progress import set_chunks_total, update_progress
from ai_portal.workers.ingest.readers import stream_text_pages

logger = logging.getLogger(__name__)


def ingest_document_worker(document_id: int, *, db: Session | None = None) -> str | None:
    """Ingest a document into chunks + embeddings with progress tracking.

    Returns None on success. Short error string on failure (never raises).
    """
    settings = get_settings()
    own_db = db is None
    if own_db:
        db = SessionLocal()

    doc: Document | None = None
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return "Document not found"

        path = Path(doc.storage_path)
        if not path.is_file():
            doc.status = "failed"
            db.commit()
            return "Stored file is missing"

        suffix = Path(doc.filename).suffix.lower()
        file_type = file_type_for_suffix(suffix)

        # Collect all text pages (streaming, memory-efficient)
        try:
            raw_pages = list(stream_text_pages(path, suffix))
        except ValueError as e:
            doc.status = "failed"
            db.commit()
            msg = str(e)
            if msg.startswith("unsupported_type:"):
                suf = msg.split(":", 1)[-1]
                return f"Unsupported file type ({suf})"
            return "Could not read file"

        if not raw_pages:
            doc.status = "failed"
            db.commit()
            return "File has no extractable text"

        # Semantic chunk all pages
        all_chunks: list[tuple[str, dict]] = []
        for page_text, page_num in raw_pages:
            all_chunks.extend(semantic_chunks(page_text, file_type, doc.filename, page_num))

        if not all_chunks:
            doc.status = "failed"
            db.commit()
            return "File has no extractable text"

        set_chunks_total(db, doc, total=len(all_chunks))

        # Embed and commit in batches
        batch_size = settings.ingest_embed_batch_size
        commit_size = settings.ingest_commit_batch_size
        chunk_index = 0
        pending: list[DocumentChunk] = []

        for batch_start in range(0, len(all_chunks), batch_size):
            batch = all_chunks[batch_start : batch_start + batch_size]
            texts = [content for content, _ in batch]

            try:
                embeddings = embedding_svc.embed_texts(texts)
            except ValueError as e:
                doc.status = "failed"
                db.commit()
                return str(e)
            except Exception:
                logger.exception("ingest_embed_failed", extra={"document_id": document_id})
                doc.status = "failed"
                db.commit()
                return "Embedding request failed"

            for (content, meta), emb in zip(batch, embeddings, strict=True):
                chunk = DocumentChunk(
                    document_id=doc.id,
                    content=content,
                    chunk_index=chunk_index,
                    meta=meta,
                    embedding=emb,
                )
                pending.append(chunk)
                chunk_index += 1

                if len(pending) >= commit_size:
                    for c in pending:
                        db.add(c)
                    db.flush()
                    for c in pending:
                        db.execute(
                            text(
                                "UPDATE document_chunks SET search_vector = to_tsvector('english', :content) "
                                "WHERE id = :id"
                            ),
                            {"content": c.content, "id": c.id},
                        )
                    update_progress(db, doc, chunks_done=chunk_index)
                    pending = []

        # Commit remaining
        if pending:
            for c in pending:
                db.add(c)
            db.flush()
            for c in pending:
                db.execute(
                    text(
                        "UPDATE document_chunks SET search_vector = to_tsvector('english', :content) "
                        "WHERE id = :id"
                    ),
                    {"content": c.content, "id": c.id},
                )
            update_progress(db, doc, chunks_done=chunk_index)

        doc.status = "ready"
        db.commit()
        return None

    except Exception:
        logger.exception("ingest_failed", extra={"document_id": document_id})
        if doc is None:
            doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = "failed"
            db.commit()
        return "Ingest failed unexpectedly"
    finally:
        if own_db:
            db.close()
