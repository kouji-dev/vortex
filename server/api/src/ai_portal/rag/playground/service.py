"""KB playground service — runs retrieval (+ optional answer) and persists."""
from __future__ import annotations

import uuid as _uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import KbPlaygroundSession
from ai_portal.rag.playground.schemas import (
    PlaygroundRequest,
    PlaygroundResponse,
    PlaygroundSessionOut,
    PlaygroundSettings,
    RetrievedChunk,
)

# (kb_id, query, top_k) -> list of retrieved chunks
RetrieveFn = Callable[[int, str, PlaygroundSettings], Awaitable[list[RetrievedChunk]]]
# (query, retrieved chunks, settings) -> answer text + citations
AnswerFn = Callable[
    [str, list[RetrievedChunk], PlaygroundSettings],
    Awaitable[tuple[str, list[dict[str, Any]]]],
]


def _settings_from_row(row: KbPlaygroundSession) -> PlaygroundSettings:
    raw = dict(row.settings_json or {})
    return PlaygroundSettings.model_validate(raw)


def _row_to_out(row: KbPlaygroundSession) -> PlaygroundSessionOut:
    return PlaygroundSessionOut(
        id=row.id,
        kb_id=row.kb_id,
        prompt=row.prompt,
        settings=_settings_from_row(row),
        retrieved=[RetrievedChunk.model_validate(c) for c in (row.retrieved_json or [])],
        answer=row.answer,
        created_at=row.created_at,
    )


class KbPlaygroundService:
    def __init__(
        self,
        db: Session,
        *,
        retrieve: RetrieveFn,
        answer: AnswerFn | None = None,
    ) -> None:
        self.db = db
        self.retrieve = retrieve
        self.answer = answer

    async def run(
        self,
        *,
        kb_id: int,
        user_id: int | None,
        req: PlaygroundRequest,
    ) -> PlaygroundResponse:
        retrieved = await self.retrieve(kb_id, req.query, req.settings)
        answer_text = ""
        citations: list[dict[str, Any]] = []
        if self.answer is not None:
            answer_text, citations = await self.answer(req.query, retrieved, req.settings)
        session_id: _uuid.UUID | None = None
        if req.save:
            row = KbPlaygroundSession(
                kb_id=kb_id,
                user_id=user_id,
                prompt=req.query,
                settings_json=req.settings.model_dump(),
                retrieved_json=[c.model_dump() for c in retrieved],
                answer=answer_text or None,
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            session_id = row.id
        return PlaygroundResponse(
            session_id=session_id,
            query=req.query,
            retrieved=retrieved,
            answer=answer_text,
            citations=citations,
        )

    def list_sessions(self, *, kb_id: int, limit: int = 50) -> list[PlaygroundSessionOut]:
        rows = self.db.scalars(
            select(KbPlaygroundSession)
            .where(KbPlaygroundSession.kb_id == kb_id)
            .order_by(KbPlaygroundSession.created_at.desc())
            .limit(limit)
        )
        return [_row_to_out(r) for r in rows]

    def get_session(
        self, *, kb_id: int, session_id: _uuid.UUID
    ) -> PlaygroundSessionOut | None:
        row = self.db.get(KbPlaygroundSession, session_id)
        if row is None or row.kb_id != kb_id:
            return None
        return _row_to_out(row)

    def delete_session(self, *, kb_id: int, session_id: _uuid.UUID) -> bool:
        row = self.db.get(KbPlaygroundSession, session_id)
        if row is None or row.kb_id != kb_id:
            return False
        self.db.delete(row)
        self.db.commit()
        return True


    def save_as_eval_record(
        self,
        *,
        kb_id: int,
        session_id: _uuid.UUID,
        test_set_id: _uuid.UUID,
    ) -> "EvalRecord | None":
        """Append this session as a new EvalRecord on ``test_set_id``.

        Returns the appended record, or ``None`` when either resource is
        missing or out-of-kb.
        """
        from ai_portal.knowledge_base.model import KbEval, KbPlaygroundSession
        from ai_portal.rag.eval.schemas import EvalRecord
        from ai_portal.rag.eval.service import _records_from_blob

        session = self.db.get(KbPlaygroundSession, session_id)
        if session is None or session.kb_id != kb_id:
            return None
        eval_row = self.db.get(KbEval, test_set_id)
        if eval_row is None or eval_row.kb_id != kb_id:
            return None

        existing = _records_from_blob(eval_row.test_set_json or {})
        # Synthesize record_id from session id (stable, idempotent).
        record = EvalRecord(
            id=f"pg-{session.id.hex[:12]}",
            query=session.prompt,
            expected_doc_ids=[
                str(c.get("document_id"))
                for c in (session.retrieved_json or [])
                if c.get("document_id")
            ],
            expected_answer=session.answer or "",
        )
        if any(r.id == record.id for r in existing):
            # Idempotent: don't duplicate. Return the same record.
            return record
        existing.append(record)
        eval_row.test_set_json = {"records": [r.model_dump() for r in existing]}
        # SQLAlchemy doesn't auto-flag JSONB mutations; mark dirty.
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(eval_row, "test_set_json")
        self.db.commit()
        self.db.refresh(eval_row)
        return record


__all__ = ["AnswerFn", "KbPlaygroundService", "RetrieveFn"]
