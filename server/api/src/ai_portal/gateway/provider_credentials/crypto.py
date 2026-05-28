"""AES-GCM encryption helpers for provider credentials.

KEK lives in ``CONTROL_PLANE_KEK`` env (base64 of 32 random bytes). Each
ciphertext is prefixed with a 12-byte random nonce. Ciphertext layout::

    base64( nonce[12] || gcm_ciphertext_with_tag )

Per-org rotation: pass a fresh key into :func:`rotate_key` to re-encrypt
every row for an org with a new KEK. Caller decrypts with the old key,
encrypts with the new — keeps blast radius small.
"""

from __future__ import annotations

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEK_ENV = "CONTROL_PLANE_KEK"
_NONCE_LEN = 12  # AES-GCM standard nonce size


class KekUnset(RuntimeError):
    """Raised when ``CONTROL_PLANE_KEK`` is empty / missing."""


def _load_kek(override: bytes | None = None) -> bytes:
    if override is not None:
        if len(override) != 32:
            raise ValueError("KEK must be 32 bytes (256 bits)")
        return override
    raw = os.environ.get(_KEK_ENV, "").strip()
    if not raw:
        raise KekUnset(
            f"{_KEK_ENV} is not set — provider credential encryption disabled. "
            "Generate with: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError(f"{_KEK_ENV} must decode to 32 bytes (got {len(key)})")
    return key


def encrypt(plaintext: str, *, kek: bytes | None = None) -> str:
    """Encrypt *plaintext* with AES-GCM. Returns base64(nonce || ct||tag)."""
    if not isinstance(plaintext, str):
        raise TypeError("plaintext must be str")
    key = _load_kek(kek)
    nonce = secrets.token_bytes(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(ciphertext_b64: str, *, kek: bytes | None = None) -> str:
    """Reverse of :func:`encrypt`."""
    key = _load_kek(kek)
    raw = base64.b64decode(ciphertext_b64.encode("ascii"))
    if len(raw) < _NONCE_LEN + 16:
        raise ValueError("ciphertext truncated")
    nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")


def rotate_key(ciphertext_b64: str, *, old_kek: bytes, new_kek: bytes) -> str:
    """Re-encrypt a single ciphertext under a new KEK. Per-org rotation hook."""
    pt = decrypt(ciphertext_b64, kek=old_kek)
    return encrypt(pt, kek=new_kek)
