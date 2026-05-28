"""Test that audit_events writes ciphertext and reads decrypted plaintext.

File-scoped — no DB. The emit_audit path is exercised by stubbing the DB
session; we assert the AuditEvent row built by the service has ``payload_enc``
populated and that the read-side helper restores the original dict.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from ai_portal.audit import event_view
from ai_portal.audit.model import AuditEvent


@pytest.fixture(autouse=True)
def _kek(monkeypatch):
    from ai_portal.core.crypto import envelope

    monkeypatch.setenv("AUDIT_KEK", Fernet.generate_key().decode("ascii"))
    envelope.reset_cache()
    yield
    envelope.reset_cache()


def test_emit_audit_writes_ciphertext(monkeypatch):
    captured = {}

    class _DummySession:
        def __init__(self):
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def execute(self, *_a, **_k):
            class _Scalar:
                def scalar_one_or_none(self_inner):
                    return None

            return _Scalar()

        def add(self, row):
            captured["row"] = row

        def commit(self):
            self.committed = True

        def refresh(self, row):
            pass

    from contextlib import contextmanager

    @contextmanager
    def _fake_bypass(_db):
        yield

    from ai_portal.audit import service as audit_service

    monkeypatch.setattr("ai_portal.core.db.session.SessionLocal", lambda: _DummySession())
    monkeypatch.setattr("ai_portal.core.db.rls.bypass_rls", _fake_bypass)
    # Skip sink fanout to keep this unit test pure.
    monkeypatch.setattr(audit_service, "_fanout_sinks", lambda *_a, **_kw: None)

    import uuid

    payload = {"target_user_id": 99, "action_details": "ban"}
    actor = {"user_id": 7, "kind": "admin"}
    result = audit_service.emit_audit(
        org_id=uuid.uuid4(),
        event_type="user.ban",
        actor=actor,
        resource={"type": "user", "id": "99"},
        payload=payload,
    )

    row = captured["row"]
    assert isinstance(row, AuditEvent)
    # JSONB plaintext columns must be blanked.
    assert row.payload_json is None
    assert row.metadata_ is None
    assert row.actor_json is None
    # Ciphertext columns must be populated.
    assert isinstance(row.payload_enc, bytes) and row.payload_enc
    assert isinstance(row.actor_enc, bytes) and row.actor_enc
    # The ciphertext must not leak the cleartext.
    assert b"target_user_id" not in row.payload_enc
    assert b"admin" not in row.actor_enc

    # The returned payload is the decrypted form.
    assert result is not None
    assert result.payload == payload
    assert result.actor_json == actor


def test_event_view_decrypt_helpers():
    from ai_portal.core.crypto import encrypt_json

    fake_row = MagicMock(spec=["payload_enc", "actor_enc", "payload_json", "metadata_", "actor_json"])
    fake_row.payload_enc = encrypt_json({"a": 1})
    fake_row.actor_enc = encrypt_json({"who": "alice"})
    fake_row.payload_json = None
    fake_row.metadata_ = None
    fake_row.actor_json = None

    assert event_view.decrypt_payload(fake_row) == {"a": 1}
    assert event_view.decrypt_actor(fake_row) == {"who": "alice"}


def test_event_view_falls_back_to_plaintext():
    """Rows written before encryption land should still read."""
    fake_row = MagicMock(spec=["payload_enc", "actor_enc", "payload_json", "metadata_", "actor_json"])
    fake_row.payload_enc = None
    fake_row.actor_enc = None
    fake_row.payload_json = {"legacy": True}
    fake_row.metadata_ = None
    fake_row.actor_json = {"who": "legacy"}

    assert event_view.decrypt_payload(fake_row) == {"legacy": True}
    assert event_view.decrypt_actor(fake_row) == {"who": "legacy"}
