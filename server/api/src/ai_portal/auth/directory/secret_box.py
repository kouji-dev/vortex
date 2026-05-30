"""Envelope encryption for the LDAP service-account bind secret.

Same KEK pattern as ``core.crypto.envelope`` (Fernet), but for a single string
secret and keyed off ``DIRECTORY_KEK`` (falling back to ``AUDIT_KEK`` so a
single deployment KEK can cover both). When no KEK is configured we store a
``plain:`` marker so dev works without a key; production MUST set a KEK.
"""

from __future__ import annotations

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_PLAIN_PREFIX = "plain:"


class SecretBoxError(RuntimeError):
    """Raised when a token is malformed or fails authentication."""


def _key() -> str:
    return (
        os.environ.get("DIRECTORY_KEK", "").strip()
        or os.environ.get("AUDIT_KEK", "").strip()
    )


def _fernet() -> Fernet | None:
    raw = _key()
    if not raw:
        return None
    try:
        return Fernet(raw.encode("ascii"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("DIRECTORY_KEK/AUDIT_KEK invalid (%s); using plain marker", exc)
        return None


def encrypt_secret(plaintext: str) -> str:
    """Encrypt ``plaintext`` to a storable token string."""
    f = _fernet()
    if f is None:
        return _PLAIN_PREFIX + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Inverse of :func:`encrypt_secret`."""
    if token.startswith(_PLAIN_PREFIX):
        try:
            return base64.b64decode(token[len(_PLAIN_PREFIX):]).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise SecretBoxError(f"plain marker decode failed: {exc}") from exc
    f = _fernet()
    if f is None:
        raise SecretBoxError("ciphertext present but no KEK configured")
    try:
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretBoxError("invalid bind-secret token") from exc


def is_configured() -> bool:
    return _fernet() is not None
