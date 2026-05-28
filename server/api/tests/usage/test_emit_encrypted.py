"""Test that emit_usage writes ciphertext columns and read helpers decrypt."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _kek(monkeypatch):
    from ai_portal.core.crypto import envelope

    monkeypatch.setenv("AUDIT_KEK", Fernet.generate_key().decode("ascii"))
    envelope.reset_cache()
    yield
    envelope.reset_cache()


def test_emit_usage_writes_ciphertext():
    """The UsageEvent built by emit_usage carries encrypted blobs, not JSON."""
    from ai_portal.usage import emit as emit_mod
    from ai_portal.usage.units import UsageUnit

    captured = {}

    class _FakeDB:
        def add(self, row):
            captured["row"] = row

        def flush(self):
            pass

    org_id = uuid.uuid4()
    meta = {"trace": "abc-123", "secret": "do-not-leak"}
    row = emit_mod.emit_usage(
        _FakeDB(),
        org_id=org_id,
        unit=UsageUnit.tokens_in.value,
        qty=10,
        actor_kind="user",
        module="gateway",
        model="claude-sonnet-4-6",
        meta=meta,
    )
    assert captured["row"] is row
    assert row.meta is None
    assert row.pricing_snapshot is None
    assert isinstance(row.meta_enc, bytes) and row.meta_enc
    assert isinstance(row.pricing_snapshot_enc, bytes) and row.pricing_snapshot_enc
    assert b"do-not-leak" not in row.meta_enc
    assert b"per_million_usd" not in row.pricing_snapshot_enc


def test_event_view_decrypts():
    from ai_portal.core.crypto import encrypt_json
    from ai_portal.usage import event_view

    fake = MagicMock(spec=["meta_enc", "pricing_snapshot_enc", "meta", "pricing_snapshot"])
    fake.meta_enc = encrypt_json({"k": "v"})
    fake.pricing_snapshot_enc = encrypt_json({"source": "override"})
    fake.meta = None
    fake.pricing_snapshot = None

    assert event_view.meta(fake) == {"k": "v"}
    assert event_view.pricing_snapshot(fake) == {"source": "override"}


def test_event_view_legacy_plaintext_fallback():
    from ai_portal.usage import event_view

    fake = MagicMock(spec=["meta_enc", "pricing_snapshot_enc", "meta", "pricing_snapshot"])
    fake.meta_enc = None
    fake.pricing_snapshot_enc = None
    fake.meta = {"legacy": True}
    fake.pricing_snapshot = {"source": "default"}

    assert event_view.meta(fake) == {"legacy": True}
    assert event_view.pricing_snapshot(fake) == {"source": "default"}
