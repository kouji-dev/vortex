"""Phase Polish-T1 — envelope encryption helpers."""
from __future__ import annotations

import os
import uuid

import pytest
from cryptography.fernet import Fernet

from ai_portal.memory import encryption


@pytest.fixture(autouse=True)
def _kek_env(monkeypatch):
    monkeypatch.setenv("MEMORY_KEK", Fernet.generate_key().decode())
    encryption._reset_kek_cache()
    yield
    encryption._reset_kek_cache()


def test_is_ciphertext_marker() -> None:
    assert encryption.is_ciphertext("enc:v1:abc")
    assert not encryption.is_ciphertext("plaintext")
    assert not encryption.is_ciphertext("")
    assert not encryption.is_ciphertext(None)


def test_generate_dek_is_fernet_key() -> None:
    dek = encryption.generate_dek()
    assert isinstance(dek, bytes)
    Fernet(dek)  # does not raise


def test_wrap_unwrap_roundtrip() -> None:
    dek = encryption.generate_dek()
    wrapped = encryption.wrap_dek(dek)
    assert isinstance(wrapped, str)
    assert wrapped != dek.decode()
    assert encryption.unwrap_dek(wrapped) == dek


def test_wrap_requires_kek(monkeypatch) -> None:
    monkeypatch.delenv("MEMORY_KEK", raising=False)
    encryption._reset_kek_cache()
    with pytest.raises(RuntimeError):
        encryption.wrap_dek(encryption.generate_dek())


def test_encrypt_decrypt_roundtrip() -> None:
    dek = encryption.generate_dek()
    cipher = encryption.encrypt_with_dek("hello world", dek)
    assert cipher.startswith(encryption.CIPHER_PREFIX)
    assert "hello world" not in cipher
    assert encryption.decrypt_with_dek(cipher, dek) == "hello world"


def test_decrypt_passthrough_for_plaintext() -> None:
    dek = encryption.generate_dek()
    assert encryption.decrypt_with_dek("not encrypted", dek) == "not encrypted"


def test_bad_kek_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("MEMORY_KEK", "not-a-fernet-key")
    encryption._reset_kek_cache()
    assert encryption._kek() is None


def test_memory_encryption_module_exports() -> None:
    for name in (
        "MemoryEncryption",
        "encrypt_with_dek",
        "decrypt_with_dek",
        "generate_dek",
        "wrap_dek",
        "unwrap_dek",
        "is_ciphertext",
        "CIPHER_PREFIX",
    ):
        assert hasattr(encryption, name), name


def test_memory_encryption_config_model_exists() -> None:
    from ai_portal.memory.model import MemoryEncryptionConfig

    cols = MemoryEncryptionConfig.__table__.columns
    for name in ("id", "org_id", "kek_ref", "wrapped_dek", "enabled"):
        assert name in cols.keys(), name


def test_memory_encryption_class_has_methods() -> None:
    import inspect

    for name in ("encrypt", "decrypt", "enable", "disable", "is_enabled"):
        m = getattr(encryption.MemoryEncryption, name)
        assert inspect.iscoroutinefunction(m), name


def test_migration_present() -> None:
    """Encryption migration shipped."""
    from pathlib import Path

    # tests/memory/test_encryption.py -> .. .. -> server/api/
    api_root = Path(__file__).resolve().parents[2]
    versions = api_root / "alembic" / "versions"
    assert (versions / "063_memory_encryption_config.py").exists()
