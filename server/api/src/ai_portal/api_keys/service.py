"""ApiKeyService — mint, verify, revoke, rotate, list.

Plaintext format: ``ap_`` + ``base62(32 random bytes)``. The prefix (``ap_`` +
the first 9 chars of the body) is stored separately so admins can identify a
key without exposing the secret. The full plaintext SHA-256 hash is stored.

Lifecycle:

- ``create`` — mints a new key. Returns :class:`CreatedApiKey` with plaintext.
- ``verify`` — given a plaintext, returns the live :class:`ApiKey` row (and
  bumps ``last_used_at``) or ``None`` if invalid / revoked / expired.
- ``revoke`` — soft-revokes; verify returns ``None`` thereafter.
- ``rotate`` — atomically mints a fresh key carrying the predecessor's scopes,
  then revokes the old one. Returns the new key + revoked id.
- ``list_for_org`` — list (newest first).

Plaintext is **never** persisted nor recoverable. Verifying compares stored
SHA-256 against the SHA-256 of the presented plaintext.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ai_portal.api_keys.model import ApiKey
from ai_portal.api_keys.repository import ApiKeyRepo


PLAINTEXT_PREFIX = "ap_"
PREFIX_BODY_LEN = 9  # chars of the random body included in the stored prefix
SECRET_BYTES = 32


# ── Errors ────────────────────────────────────────────────────────────────────


class ApiKeyNotFound(Exception):
    """Raised when a key id is not present in the caller's org."""


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CreatedApiKey:
    """Return shape for :meth:`ApiKeyService.create`.

    ``plaintext`` is only accessible on this struct and only at creation time.
    """

    key: ApiKey
    plaintext: str


# ── Plaintext helpers ────────────────────────────────────────────────────────


_BASE62_ALPHABET = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
)


def _b62_encode(b: bytes) -> str:
    """Encode bytes as base62 string. Plain integer-base conversion."""
    n = int.from_bytes(b, "big") if b else 0
    if n == 0:
        return _BASE62_ALPHABET[0]
    out: list[str] = []
    while n:
        n, rem = divmod(n, 62)
        out.append(_BASE62_ALPHABET[rem])
    return "".join(reversed(out))


def mint_plaintext() -> str:
    """Mint a fresh secret: ``ap_<base62(32 random bytes)>``."""
    body = _b62_encode(secrets.token_bytes(SECRET_BYTES))
    return PLAINTEXT_PREFIX + body


def hash_plaintext(plaintext: str) -> str:
    """SHA-256 hex digest of ``plaintext`` — the stored form."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def split_prefix(plaintext: str) -> str:
    """Short identifier shown to users (``ap_xxxxxxxxx``)."""
    # Plaintext = "ap_" + body. We expose the prefix + first 9 body chars.
    body = plaintext[len(PLAINTEXT_PREFIX):]
    return PLAINTEXT_PREFIX + body[:PREFIX_BODY_LEN]


# ── Service ──────────────────────────────────────────────────────────────────


class ApiKeyService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ApiKeyRepo(db)

    # ── create ──────────────────────────────────────────────────────────

    def create(
        self,
        *,
        org_id: _uuid.UUID,
        name: str,
        scopes: list[str] | None = None,
        actor_user_id: int | None = None,
        expires_at: datetime | None = None,
    ) -> CreatedApiKey:
        plaintext = mint_plaintext()
        key = ApiKey(
            org_id=org_id,
            actor_user_id=actor_user_id,
            name=name,
            prefix=split_prefix(plaintext),
            hash=hash_plaintext(plaintext),
            scopes_json=list(scopes or []),
            expires_at=expires_at,
        )
        self.repo.add(key)
        self.db.commit()
        self.db.refresh(key)
        return CreatedApiKey(key=key, plaintext=plaintext)

    # ── verify ──────────────────────────────────────────────────────────

    def verify(self, plaintext: str) -> ApiKey | None:
        """Return the live :class:`ApiKey` for *plaintext* or ``None``.

        ``None`` covers: unknown hash, malformed prefix, revoked, expired.
        """
        if not plaintext or not plaintext.startswith(PLAINTEXT_PREFIX):
            return None
        digest = hash_plaintext(plaintext)
        row = self.repo.by_hash(digest)
        if row is None:
            return None
        now = datetime.now(UTC)
        if row.revoked_at is not None:
            return None
        if row.expires_at is not None and row.expires_at <= now:
            return None
        row.last_used_at = now
        self.db.commit()
        return row

    # ── revoke ──────────────────────────────────────────────────────────

    def revoke(self, *, org_id: _uuid.UUID, key_id: _uuid.UUID) -> ApiKey:
        row = self.repo.by_id(org_id=org_id, key_id=key_id)
        if row is None:
            raise ApiKeyNotFound(str(key_id))
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(row)
        return row

    # ── rotate ──────────────────────────────────────────────────────────

    def rotate(self, *, org_id: _uuid.UUID, key_id: _uuid.UUID) -> tuple[CreatedApiKey, _uuid.UUID]:
        """Mint a replacement key carrying the same scopes; revoke the old one.

        Returns ``(new_created, revoked_id)``.
        """
        old = self.repo.by_id(org_id=org_id, key_id=key_id)
        if old is None:
            raise ApiKeyNotFound(str(key_id))
        new_created = self.create(
            org_id=org_id,
            name=old.name,
            scopes=list(old.scopes_json or []),
            actor_user_id=old.actor_user_id,
            expires_at=old.expires_at,
        )
        # Revoke old after the new row is committed so verify can't briefly hit
        # neither.
        if old.revoked_at is None:
            old.revoked_at = datetime.now(UTC)
            self.db.commit()
        return new_created, old.id

    # ── list ────────────────────────────────────────────────────────────

    def list_for_org(self, org_id: _uuid.UUID) -> Sequence[ApiKey]:
        return self.repo.list_for_org(org_id)

    def get(self, *, org_id: _uuid.UUID, key_id: _uuid.UUID) -> ApiKey:
        row = self.repo.by_id(org_id=org_id, key_id=key_id)
        if row is None:
            raise ApiKeyNotFound(str(key_id))
        return row
