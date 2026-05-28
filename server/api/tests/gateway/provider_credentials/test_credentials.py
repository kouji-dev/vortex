"""A4: provider credentials — AES-GCM at rest, decrypt via service helper."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC

import pytest
from sqlalchemy import text

# Ensure all referenced tables are loaded before flush.
import ai_portal.auth.model  # noqa: F401
import ai_portal.gateway.provider_credentials.model  # noqa: F401
from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'PC') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


@pytest.fixture(autouse=True)
def _kek(monkeypatch):
    """Stable KEK for the whole test file."""
    key = base64.b64encode(b"\x11" * 32).decode("ascii")
    monkeypatch.setenv("CONTROL_PLANE_KEK", key)
    yield


def test_encrypt_decrypt_roundtrip():
    from ai_portal.gateway.provider_credentials.crypto import decrypt, encrypt

    ct = encrypt("sk-secret-12345")
    assert ct != "sk-secret-12345"
    assert decrypt(ct) == "sk-secret-12345"
    # Nonces fresh → ciphertext changes between calls
    assert encrypt("sk-secret-12345") != ct


def test_kek_unset_raises(monkeypatch):
    from ai_portal.gateway.provider_credentials.crypto import KekUnset, encrypt

    monkeypatch.delenv("CONTROL_PLANE_KEK", raising=False)
    with pytest.raises(KekUnset):
        encrypt("anything")


def test_rotate_key_re_encrypts_under_new_kek():
    from ai_portal.gateway.provider_credentials.crypto import (
        decrypt,
        encrypt,
        rotate_key,
    )

    old = b"\x11" * 32
    new = b"\x22" * 32
    ct_old = encrypt("sk-orig", kek=old)
    ct_new = rotate_key(ct_old, old_kek=old, new_kek=new)
    assert ct_new != ct_old
    assert decrypt(ct_new, kek=new) == "sk-orig"
    with pytest.raises(Exception):
        decrypt(ct_new, kek=old)


@requires_postgres
def test_service_upsert_stores_ciphertext_get_decrypted_returns_plaintext():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.provider_credentials.model import ProviderCredential
    from ai_portal.gateway.provider_credentials.service import (
        ProviderCredentialService,
    )

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "pc-roundtrip")
            svc = ProviderCredentialService(db)
            row = svc.upsert(
                org_id=org_id,
                provider="anthropic",
                plaintext="sk-ant-xyz",
            )
            db.flush()

            # Raw DB column must be ciphertext — never plaintext.
            raw_ct = db.execute(
                text(
                    "SELECT credentials_encrypted FROM provider_credentials "
                    "WHERE id = :id"
                ),
                {"id": str(row.id)},
            ).scalar_one()
            assert raw_ct != "sk-ant-xyz"
            assert "sk-ant-xyz" not in raw_ct
            assert len(raw_ct) > 20  # base64 ciphertext

            # Service helper decrypts back to plaintext.
            assert (
                svc.get_decrypted(org_id=org_id, provider="anthropic")
                == "sk-ant-xyz"
            )

            # Upsert again with new plaintext → row replaced, healthy reset.
            row.healthy = True
            db.flush()
            svc.upsert(
                org_id=org_id,
                provider="anthropic",
                plaintext="sk-ant-new",
            )
            db.flush()
            assert (
                svc.get_decrypted(org_id=org_id, provider="anthropic")
                == "sk-ant-new"
            )
            from sqlalchemy import select as _sel

            refreshed = db.scalars(
                _sel(ProviderCredential).where(
                    ProviderCredential.org_id == org_id
                )
            ).first()
            assert refreshed is not None
            # Healthy flag reset on key change.
            assert refreshed.healthy is False

            db.execute(
                text("DELETE FROM provider_credentials WHERE org_id = :o"),
                {"o": str(org_id)},
            )
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_service_health_probe_updates_row():
    import asyncio
    from datetime import datetime

    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.provider_credentials.service import (
        HealthResult,
        ProviderCredentialService,
    )

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "pc-health")
            svc = ProviderCredentialService(db)
            svc.upsert(
                org_id=org_id,
                provider="anthropic",
                plaintext="sk-ant-healthy",
            )
            db.flush()

            now = datetime.now(UTC)
            seen_secret: list[str] = []

            async def stub_probe(secret: str) -> HealthResult:
                seen_secret.append(secret)
                return HealthResult(True, now, "")

            result = asyncio.run(
                svc.check_health(
                    org_id=org_id,
                    provider="anthropic",
                    probe=stub_probe,
                )
            )
            assert result.healthy is True
            assert seen_secret == ["sk-ant-healthy"]

            row = svc.get(org_id=org_id, provider="anthropic")
            assert row.healthy is True
            assert row.last_health_at is not None

            db.execute(
                text("DELETE FROM provider_credentials WHERE org_id = :o"),
                {"o": str(org_id)},
            )
            db.commit()
    finally:
        db.rollback()
        db.close()
