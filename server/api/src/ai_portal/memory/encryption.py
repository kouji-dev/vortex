"""Per-org envelope encryption for memory.text.

Two-tier crypto:
- KEK (key-encryption-key) lives outside the DB. Source of truth is the
  ``MEMORY_KEK`` env var (Fernet-encoded). Production deployments swap this
  for a KMS-backed handle.
- DEK (data-encryption-key) is a per-org Fernet key generated on first use,
  wrapped by KEK, persisted as ``MemoryEncryptionConfig.wrapped_dek``.

Opt-in per org via ``MemoryEncryptionConfig.enabled`` row. When disabled,
``encrypt_text`` and ``decrypt_text`` are no-ops.

Cipher format on disk:
    "enc:v1:" + base64(fernet_token)
Plain text is stored as-is when encryption is off or the row predates opt-in.
"""
from __future__ import annotations

import base64
import logging
import os
import uuid as _uuid
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CIPHER_PREFIX = "enc:v1:"


# ── KEK resolution ───────────────────────────────────────────────────────────


def _kek_from_env() -> bytes | None:
    raw = os.environ.get("MEMORY_KEK")
    if not raw:
        return None
    try:
        # validate it's a proper Fernet key
        Fernet(raw.encode("utf-8") if isinstance(raw, str) else raw)
    except Exception:
        logger.warning("memory.encryption.bad_kek")
        return None
    return raw.encode("utf-8") if isinstance(raw, str) else raw


@lru_cache(maxsize=1)
def _kek() -> Fernet | None:
    raw = _kek_from_env()
    if raw is None:
        return None
    return Fernet(raw)


def _reset_kek_cache() -> None:
    """Test hook — clears LRU so a freshly-set env var is picked up."""
    _kek.cache_clear()


# ── DEK lifecycle ────────────────────────────────────────────────────────────


def generate_dek() -> bytes:
    """Make a fresh Fernet key (random, 32 byte url-safe base64)."""
    return Fernet.generate_key()


def wrap_dek(dek: bytes) -> str:
    kek = _kek()
    if kek is None:
        raise RuntimeError("MEMORY_KEK not set — cannot wrap DEK")
    return kek.encrypt(dek).decode("utf-8")


def unwrap_dek(wrapped: str) -> bytes:
    kek = _kek()
    if kek is None:
        raise RuntimeError("MEMORY_KEK not set — cannot unwrap DEK")
    return kek.decrypt(wrapped.encode("utf-8"))


# ── cipher format ────────────────────────────────────────────────────────────


def is_ciphertext(value: str | None) -> bool:
    return bool(value) and value.startswith(CIPHER_PREFIX)


def encrypt_with_dek(plaintext: str, dek: bytes) -> str:
    if plaintext is None:
        return plaintext
    token = Fernet(dek).encrypt(plaintext.encode("utf-8"))
    return CIPHER_PREFIX + base64.urlsafe_b64encode(token).decode("ascii")


def decrypt_with_dek(value: str, dek: bytes) -> str:
    if not is_ciphertext(value):
        return value
    raw = value[len(CIPHER_PREFIX) :]
    try:
        token = base64.urlsafe_b64decode(raw.encode("ascii"))
        return Fernet(dek).decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError) as exc:  # pragma: no cover — invariant guard
        raise RuntimeError("memory.encryption.decrypt_failed") from exc


# ── high-level service ──────────────────────────────────────────────────────


class MemoryEncryption:
    """Per-session helper that lazily loads and caches the org DEK."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session
        self._cache: dict[_uuid.UUID, tuple[bool, Optional[bytes]]] = {}

    async def _load_config(self, org_id: _uuid.UUID) -> tuple[bool, Optional[bytes]]:
        # Late import to avoid module cycle (model imports nothing from us).
        from ai_portal.memory.model import MemoryEncryptionConfig

        if org_id in self._cache:
            return self._cache[org_id]
        row = (
            await self.s.execute(
                select(MemoryEncryptionConfig).where(
                    MemoryEncryptionConfig.org_id == org_id
                )
            )
        ).scalar_one_or_none()
        if row is None or not row.enabled or not row.wrapped_dek:
            self._cache[org_id] = (False, None)
            return self._cache[org_id]
        try:
            dek = unwrap_dek(row.wrapped_dek)
        except Exception:
            logger.exception("memory.encryption.unwrap_failed")
            self._cache[org_id] = (False, None)
            return self._cache[org_id]
        self._cache[org_id] = (True, dek)
        return self._cache[org_id]

    async def is_enabled(self, org_id: _uuid.UUID) -> bool:
        enabled, _ = await self._load_config(org_id)
        return enabled

    async def encrypt(self, org_id: _uuid.UUID, plaintext: str) -> str:
        enabled, dek = await self._load_config(org_id)
        if not enabled or dek is None:
            return plaintext
        return encrypt_with_dek(plaintext, dek)

    async def decrypt(self, org_id: _uuid.UUID, value: str) -> str:
        if not is_ciphertext(value):
            return value
        _, dek = await self._load_config(org_id)
        if dek is None:
            # row was encrypted previously but config now disabled / DEK missing
            return value
        return decrypt_with_dek(value, dek)

    async def enable(self, org_id: _uuid.UUID, kek_ref: str = "env:MEMORY_KEK") -> None:
        """Create / activate an encryption config for an org. Generates DEK."""
        from ai_portal.memory.model import MemoryEncryptionConfig

        row = (
            await self.s.execute(
                select(MemoryEncryptionConfig).where(
                    MemoryEncryptionConfig.org_id == org_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            dek = generate_dek()
            row = MemoryEncryptionConfig(
                org_id=org_id,
                kek_ref=kek_ref,
                wrapped_dek=wrap_dek(dek),
                enabled=True,
            )
            self.s.add(row)
        else:
            if not row.wrapped_dek:
                row.wrapped_dek = wrap_dek(generate_dek())
            row.kek_ref = kek_ref
            row.enabled = True
        await self.s.flush()
        self._cache.pop(org_id, None)

    async def disable(self, org_id: _uuid.UUID) -> None:
        from ai_portal.memory.model import MemoryEncryptionConfig

        row = (
            await self.s.execute(
                select(MemoryEncryptionConfig).where(
                    MemoryEncryptionConfig.org_id == org_id
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            row.enabled = False
            await self.s.flush()
        self._cache.pop(org_id, None)


__all__ = [
    "CIPHER_PREFIX",
    "MemoryEncryption",
    "decrypt_with_dek",
    "encrypt_with_dek",
    "generate_dek",
    "is_ciphertext",
    "unwrap_dek",
    "wrap_dek",
]
