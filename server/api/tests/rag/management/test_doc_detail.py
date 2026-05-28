"""Document-detail serializer — pure stand-in rows, no DB.

Locks the shape returned by ``GET /api/kbs/{id}/documents/{doc_id}`` and
the join behaviour against ``kb_sync_errors``.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from ai_portal.rag.management.doc_detail import (
    DocDetailOut,
    serialize_doc_detail,
    to_out,
)


def _doc(**overrides):
    base = dict(
        id=_uuid.uuid4(),
        kb_id=42,
        source_uri="s3://bucket/key",
        title="Doc One",
        status="failed",
        quarantine_reason="checksum mismatch",
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _err(**overrides):
    base = dict(
        run_id=_uuid.uuid4(),
        error="HTTP 500 from upstream",
        created_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_serializer_with_error_attaches_last_error_and_run_id() -> None:
    doc = _doc()
    err = _err()
    row = serialize_doc_detail(doc, err)
    assert row.id == doc.id
    assert row.kb_id == 42
    assert row.quarantine_reason == "checksum mismatch"
    assert row.last_error == "HTTP 500 from upstream"
    assert row.sync_run_id == err.run_id
    assert row.last_error_at == err.created_at


def test_serializer_without_error_leaves_fields_null() -> None:
    doc = _doc()
    row = serialize_doc_detail(doc, None)
    assert row.last_error is None
    assert row.sync_run_id is None
    assert row.last_error_at is None
    assert row.quarantine_reason == "checksum mismatch"


def test_to_out_stringifies_uuids() -> None:
    doc = _doc()
    err = _err()
    row = serialize_doc_detail(doc, err)
    out: DocDetailOut = to_out(row)
    assert out.id == str(doc.id)
    assert out.sync_run_id == str(err.run_id)
    assert out.last_error == "HTTP 500 from upstream"
    assert out.kb_id == 42


def test_to_out_handles_no_sync_error() -> None:
    doc = _doc(quarantine_reason=None)
    row = serialize_doc_detail(doc, None)
    out = to_out(row)
    assert out.quarantine_reason is None
    assert out.sync_run_id is None
    assert out.last_error is None


def test_serializer_handles_missing_optional_fields() -> None:
    doc = SimpleNamespace(
        id=_uuid.uuid4(),
        kb_id=7,
        source_uri="",
        title="",
        status="ingesting",
        quarantine_reason=None,
        created_at=None,
        updated_at=None,
    )
    row = serialize_doc_detail(doc, None)
    assert row.source_uri == ""
    assert row.title == ""
    assert row.status == "ingesting"
    assert row.created_at is None
