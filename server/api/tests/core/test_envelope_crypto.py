"""File-scoped tests for envelope encryption helpers."""

from __future__ import annotations

import base64

import pytest
from cryptography.fernet import Fernet

from ai_portal.core.crypto import envelope


@pytest.fixture(autouse=True)
def _reset_cache():
    envelope.reset_cache()
    yield
    envelope.reset_cache()


def test_none_passthrough():
    assert envelope.encrypt_json(None) is None
    assert envelope.decrypt_json(None) is None


def test_roundtrip_with_kek(monkeypatch):
    monkeypatch.setenv("AUDIT_KEK", Fernet.generate_key().decode("ascii"))
    envelope.reset_cache()
    src = {"actor": "user-42", "ip": "1.2.3.4", "list": [1, 2, 3]}
    tok = envelope.encrypt_json(src)
    assert isinstance(tok, bytes) and tok  # non-empty bytes
    assert b"actor" not in tok  # ciphertext doesn't leak the cleartext
    out = envelope.decrypt_json(tok)
    assert out == src


def test_plain_fallback_when_no_kek(monkeypatch):
    monkeypatch.delenv("AUDIT_KEK", raising=False)
    envelope.reset_cache()
    src = {"k": "v"}
    tok = envelope.encrypt_json(src)
    assert tok is not None
    assert tok.startswith(b"plain:")
    assert envelope.decrypt_json(tok) == src
    assert envelope.is_configured() is False


def test_ciphertext_without_key_raises(monkeypatch):
    # encrypt with KEK
    monkeypatch.setenv("AUDIT_KEK", Fernet.generate_key().decode("ascii"))
    envelope.reset_cache()
    tok = envelope.encrypt_json({"a": 1})
    # now strip KEK and attempt decrypt — must fail loud
    monkeypatch.delenv("AUDIT_KEK", raising=False)
    envelope.reset_cache()
    with pytest.raises(envelope.EnvelopeError):
        envelope.decrypt_json(tok)


def test_invalid_kek_falls_back_to_plain(monkeypatch):
    monkeypatch.setenv("AUDIT_KEK", "not-a-valid-fernet-key")
    envelope.reset_cache()
    src = {"x": 1}
    tok = envelope.encrypt_json(src)
    assert tok is not None and tok.startswith(b"plain:")
    assert envelope.decrypt_json(tok) == src


def test_decrypt_garbage_raises(monkeypatch):
    monkeypatch.setenv("AUDIT_KEK", Fernet.generate_key().decode("ascii"))
    envelope.reset_cache()
    with pytest.raises(envelope.EnvelopeError):
        envelope.decrypt_json(b"plain:" + base64.b64encode(b"\x00not-json"))


def test_memoryview_input(monkeypatch):
    monkeypatch.setenv("AUDIT_KEK", Fernet.generate_key().decode("ascii"))
    envelope.reset_cache()
    src = [1, 2]
    tok = envelope.encrypt_json(src)
    assert envelope.decrypt_json(memoryview(tok)) == src
