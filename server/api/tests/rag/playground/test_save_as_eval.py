"""Playground session → eval test set: save_as_eval_record."""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime

import pytest

from ai_portal.knowledge_base.model import KbEval, KbPlaygroundSession
from ai_portal.rag.playground.service import KbPlaygroundService


class _FakeDB:
    """Minimal in-memory store keyed by (model, id)."""

    def __init__(self) -> None:
        self._store: dict[tuple[type, _uuid.UUID], object] = {}
        self.commits = 0

    def store(self, obj) -> None:
        self._store[(type(obj), obj.id)] = obj

    def get(self, model, obj_id):
        return self._store.get((model, obj_id))

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, obj) -> None:
        pass


def _session(*, kb_id: int, prompt: str = "Q?", retrieved=None, answer: str | None = None):
    s = KbPlaygroundSession(
        kb_id=kb_id,
        user_id=1,
        prompt=prompt,
        settings_json={},
        retrieved_json=retrieved or [],
        answer=answer,
    )
    s.id = _uuid.uuid4()
    s.created_at = datetime.now(UTC)
    return s


def _eval(*, kb_id: int, records=None):
    e = KbEval(
        kb_id=kb_id,
        name="my-tests",
        test_set_json={"records": records or []},
    )
    e.id = _uuid.uuid4()
    e.created_at = datetime.now(UTC)
    e.updated_at = datetime.now(UTC)
    return e


async def _retrieve(*a, **k):  # unused but required by constructor
    return []


def test_save_as_eval_record_appends_record():
    db = _FakeDB()
    sess = _session(
        kb_id=5,
        prompt="What is X?",
        retrieved=[
            {"chunk_id": "c1", "document_id": "d1", "text": "...", "score": 0.9, "meta": {}},
            {"chunk_id": "c2", "document_id": "d2", "text": "...", "score": 0.7, "meta": {}},
        ],
        answer="X is foo.",
    )
    ev = _eval(kb_id=5)
    db.store(sess)
    db.store(ev)

    svc = KbPlaygroundService(db=db, retrieve=_retrieve)
    rec = svc.save_as_eval_record(kb_id=5, session_id=sess.id, test_set_id=ev.id)
    assert rec is not None
    assert rec.query == "What is X?"
    assert rec.expected_doc_ids == ["d1", "d2"]
    assert rec.expected_answer == "X is foo."
    # eval row was updated with the new record
    saved = ev.test_set_json["records"]
    assert len(saved) == 1
    assert saved[0]["id"] == rec.id
    assert db.commits == 1


def test_save_as_eval_record_session_missing_returns_none():
    db = _FakeDB()
    ev = _eval(kb_id=1)
    db.store(ev)
    svc = KbPlaygroundService(db=db, retrieve=_retrieve)
    assert svc.save_as_eval_record(kb_id=1, session_id=_uuid.uuid4(), test_set_id=ev.id) is None
    assert db.commits == 0


def test_save_as_eval_record_session_wrong_kb_returns_none():
    db = _FakeDB()
    sess = _session(kb_id=5)
    ev = _eval(kb_id=99)
    db.store(sess)
    db.store(ev)
    svc = KbPlaygroundService(db=db, retrieve=_retrieve)
    # kb_id mismatch with eval row
    assert svc.save_as_eval_record(kb_id=5, session_id=sess.id, test_set_id=ev.id) is None


def test_save_as_eval_record_eval_missing_returns_none():
    db = _FakeDB()
    sess = _session(kb_id=1)
    db.store(sess)
    svc = KbPlaygroundService(db=db, retrieve=_retrieve)
    assert svc.save_as_eval_record(kb_id=1, session_id=sess.id, test_set_id=_uuid.uuid4()) is None


def test_save_as_eval_record_is_idempotent():
    db = _FakeDB()
    sess = _session(kb_id=5, retrieved=[{"document_id": "d1"}])
    ev = _eval(kb_id=5)
    db.store(sess)
    db.store(ev)
    svc = KbPlaygroundService(db=db, retrieve=_retrieve)
    r1 = svc.save_as_eval_record(kb_id=5, session_id=sess.id, test_set_id=ev.id)
    r2 = svc.save_as_eval_record(kb_id=5, session_id=sess.id, test_set_id=ev.id)
    assert r1 is not None and r2 is not None
    assert r1.id == r2.id
    # Only one record stored (no duplicates).
    assert len(ev.test_set_json["records"]) == 1


def test_save_as_eval_record_appends_to_existing_records():
    db = _FakeDB()
    sess = _session(kb_id=5, prompt="new question")
    ev = _eval(kb_id=5, records=[{"id": "existing", "query": "prev"}])
    db.store(sess)
    db.store(ev)
    svc = KbPlaygroundService(db=db, retrieve=_retrieve)
    rec = svc.save_as_eval_record(kb_id=5, session_id=sess.id, test_set_id=ev.id)
    assert rec is not None
    records = ev.test_set_json["records"]
    assert len(records) == 2
    assert records[0]["id"] == "existing"
    assert records[1]["query"] == "new question"
