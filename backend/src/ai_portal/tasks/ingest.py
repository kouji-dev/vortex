from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy.orm import Session

from ai_portal.db.session import SessionLocal
from ai_portal.models import Document, DocumentChunk
from ai_portal.services import embedding as embedding_svc

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800


def _chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    for i in range(0, len(text), CHUNK_SIZE):
        part = text[i : i + CHUNK_SIZE].strip()
        if part:
            chunks.append(part)
    return chunks


def _read_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"unsupported_type:{suffix}")


def ingest_document(document_id: int) -> str | None:
    """Ingest a stored upload into chunks + embeddings.

    Returns ``None`` on success. On failure, updates ``Document.status`` to ``failed``,
    commits, and returns a short message suitable for API clients (never raises for
    expected failures — avoids HTTP 500 on upload when e.g. embeddings are not configured).
    """
    db: Session = SessionLocal()
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

        try:
            raw = _read_document_text(path)
        except ValueError as e:
            doc.status = "failed"
            db.commit()
            msg = str(e)
            if msg.startswith("unsupported_type:"):
                suf = msg.split(":", 1)[-1]
                return f"Unsupported file type ({suf})"
            return "Could not read file"

        parts = _chunk_text(raw)
        if not parts:
            doc.status = "failed"
            db.commit()
            return "File has no extractable text"

        try:
            embeddings = embedding_svc.embed_texts(parts)
        except ValueError as e:
            doc.status = "failed"
            db.commit()
            return str(e)
        except Exception:
            logger.exception("ingest_embed_failed", extra={"document_id": document_id})
            doc.status = "failed"
            db.commit()
            return "Embedding request failed"

        for i, (content, emb) in enumerate(zip(parts, embeddings, strict=True)):
            db.add(
                DocumentChunk(
                    document_id=doc.id,
                    content=content,
                    chunk_index=i,
                    meta={"source": doc.filename},
                    embedding=emb,
                )
            )
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
        db.close()
