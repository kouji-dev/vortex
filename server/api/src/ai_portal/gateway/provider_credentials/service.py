"""Provider credential service — CRUD + decrypt + health probe."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.gateway.provider_credentials.crypto import decrypt, encrypt
from ai_portal.gateway.provider_credentials.model import ProviderCredential

logger = logging.getLogger(__name__)


class CredentialNotFound(Exception):
    """Raised when ``get_decrypted`` finds no matching row."""


@dataclass(frozen=True)
class HealthResult:
    healthy: bool
    checked_at: datetime
    reason: str = ""


# Provider → ``GET /models`` (or equivalent) probe.
# Each entry returns ``(url, header_builder)`` where header_builder takes the
# decrypted secret and yields the auth header dict.
_HEALTH_PROBES: dict[str, tuple[str, Callable[[str], dict[str, str]]]] = {
    "anthropic": (
        "https://api.anthropic.com/v1/models",
        lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"},
    ),
    "openai": (
        "https://api.openai.com/v1/models",
        lambda key: {"Authorization": f"Bearer {key}"},
    ),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/models",
        lambda key: {"x-goog-api-key": key},
    ),
}


class ProviderCredentialService:
    """CRUD + decrypt-on-demand for ``provider_credentials``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── write ──────────────────────────────────────────────────────────────
    def upsert(
        self,
        *,
        org_id: UUID,
        provider: str,
        plaintext: str,
        label: str = "default",
    ) -> ProviderCredential:
        """Insert or replace the credential row. Stores ciphertext only."""
        row = self.db.scalars(
            select(ProviderCredential)
            .where(ProviderCredential.org_id == org_id)
            .where(ProviderCredential.provider == provider)
            .where(ProviderCredential.label == label)
        ).first()
        ct = encrypt(plaintext)
        if row is None:
            row = ProviderCredential(
                org_id=org_id,
                provider=provider,
                label=label,
                credentials_encrypted=ct,
            )
            self.db.add(row)
        else:
            row.credentials_encrypted = ct
            # Force healthy=False until next probe.
            row.healthy = False
            row.last_health_at = None
        self.db.flush()
        return row

    def delete(self, *, org_id: UUID, credential_id: UUID) -> None:
        row = self.db.scalars(
            select(ProviderCredential)
            .where(ProviderCredential.org_id == org_id)
            .where(ProviderCredential.id == credential_id)
        ).first()
        if row is None:
            raise CredentialNotFound(str(credential_id))
        self.db.delete(row)
        self.db.flush()

    # ── read ───────────────────────────────────────────────────────────────
    def list_for_org(self, org_id: UUID) -> list[ProviderCredential]:
        return list(
            self.db.scalars(
                select(ProviderCredential)
                .where(ProviderCredential.org_id == org_id)
                .order_by(ProviderCredential.provider, ProviderCredential.label)
            ).all()
        )

    def get(
        self, *, org_id: UUID, provider: str, label: str = "default"
    ) -> ProviderCredential:
        row = self.db.scalars(
            select(ProviderCredential)
            .where(ProviderCredential.org_id == org_id)
            .where(ProviderCredential.provider == provider)
            .where(ProviderCredential.label == label)
        ).first()
        if row is None:
            raise CredentialNotFound(f"{provider}/{label}")
        return row

    def get_decrypted(
        self, *, org_id: UUID, provider: str, label: str = "default"
    ) -> str:
        """Decrypt and return the raw secret. Use sparingly."""
        row = self.get(org_id=org_id, provider=provider, label=label)
        return decrypt(row.credentials_encrypted)

    # ── health ─────────────────────────────────────────────────────────────
    async def check_health(
        self,
        *,
        org_id: UUID,
        provider: str,
        label: str = "default",
        probe: Callable[[str], Awaitable[HealthResult]] | None = None,
    ) -> HealthResult:
        """Probe ``GET /models`` (or equivalent). Updates ``healthy`` + ``last_health_at``."""
        row = self.get(org_id=org_id, provider=provider, label=label)
        secret = decrypt(row.credentials_encrypted)

        if probe is not None:
            result = await probe(secret)
        else:
            result = await _default_probe(provider, secret)

        row.healthy = result.healthy
        row.last_health_at = result.checked_at
        self.db.flush()
        return result


async def _default_probe(provider: str, secret: str) -> HealthResult:
    """Default probe — GET each provider's models list endpoint."""
    spec = _HEALTH_PROBES.get(provider)
    now = datetime.now(UTC)
    if spec is None:
        return HealthResult(False, now, f"no probe registered for provider={provider}")
    url, build_headers = spec
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=build_headers(secret))
        ok = 200 <= resp.status_code < 300
        return HealthResult(ok, now, "" if ok else f"http {resp.status_code}")
    except Exception as exc:  # pragma: no cover — exercised by integration tests
        return HealthResult(False, now, f"{type(exc).__name__}: {exc}")


def register_health_probe(
    provider: str,
    url: str,
    header_builder: Callable[[str], dict[str, str]],
) -> None:
    """Register or override a provider's health probe.

    Used by new providers landed via the protocol refactor (Task A2).
    """
    _HEALTH_PROBES[provider] = (url, header_builder)


__all__: list[str] = [
    "CredentialNotFound",
    "HealthResult",
    "ProviderCredentialService",
    "register_health_probe",
]
