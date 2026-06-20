from __future__ import annotations

import os
import socket
import uuid as _uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Auto-provide SCRATCH_DATABASE_URL from DATABASE_URL when not already set.
# Enables test_alembic_clean_upgrade.py without requiring manual env export.
# Uses the same Postgres server as DATABASE_URL but a throwaway scratch DB.
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url and "SCRATCH_DATABASE_URL" not in os.environ:
    from sqlalchemy.engine.url import make_url as _make_url
    try:
        _scratch = _make_url(_db_url).set(database="ai_portal_scratch").render_as_string(hide_password=False)
        os.environ["SCRATCH_DATABASE_URL"] = _scratch
    except Exception:
        pass

# Hosts no test may ever reach — real LLM/embedding/rerank APIs cost money.
# Tests mock at the boundary (respx / a provider fixture); a real DNS lookup to
# one of these fails loud instead of silently spending.
_BLOCKED_LLM_HOSTS = (
    "api.openai.com",
    "api.anthropic.com",
    "api.voyageai.com",
    "api.cohere.com",
    "generativelanguage.googleapis.com",
)


@pytest.fixture(autouse=True)
def _block_real_llm_network(monkeypatch):
    """Fail loud if a test tries a real provider call. Mock it instead."""
    real_getaddrinfo = socket.getaddrinfo

    def guard(host, *args, **kwargs):
        if isinstance(host, str) and any(
            host == h or host.endswith("." + h) for h in _BLOCKED_LLM_HOSTS
        ):
            raise RuntimeError(
                f"real LLM call blocked in tests: {host} — mock it (respx / provider fixture)"
            )
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guard)


def _postgres_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def postgres_available() -> bool:
    url = _postgres_url()
    if not url:
        return False
    try:
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OSError:
        return False
    return True


requires_postgres = pytest.mark.skipif(
    False,
    reason="postgres required; tests must not skip",
)


@pytest.fixture
def db_session():
    from ai_portal.core.db.session import SessionLocal
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.rollback(); db.close()


@pytest.fixture
def org(db_session):
    from ai_portal.auth.model import Org
    o = Org(slug=f"acme-{_uuid.uuid4().hex[:8]}", name="Acme")
    db_session.add(o); db_session.flush(); return o


@pytest.fixture
def rsa_key():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def mock_jwks_client(rsa_key):
    """Bypass PyJWKClient's urllib fetch: pre-populate the global cache with a fake
    client that returns a signing key built from the test RSA key (kid 'k1')."""
    import json as _json
    import jwt as _jwt
    from unittest.mock import MagicMock
    from jwt import PyJWK
    import ai_portal.auth.oidc.jwks as _jwks_mod

    jwk = _json.loads(_jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key()))
    jwk["kid"] = "k1"
    fake = MagicMock()
    fake.get_signing_key_from_jwt.return_value = PyJWK.from_dict(jwk)
    saved = dict(_jwks_mod._clients)
    # any jwks_uri used in tests resolves to the same fake client
    _jwks_mod._clients.clear()
    orig_client = _jwks_mod._client
    _jwks_mod._client = lambda uri: fake
    yield fake
    _jwks_mod._client = orig_client
    _jwks_mod._clients.clear()
    _jwks_mod._clients.update(saved)


@pytest.fixture(scope="module")
def sync_engine():
    url = _postgres_url()
    if not url:
        pytest.fail("DATABASE_URL not set or Postgres unreachable")
    # Replace async driver with sync psycopg driver if needed
    sync_url = url.replace("+asyncpg", "+psycopg").replace(
        "postgresql+psycopg2", "postgresql+psycopg"
    )
    if not sync_url.startswith("postgresql"):
        pytest.fail("DATABASE_URL not set or Postgres unreachable")
    eng = create_engine(sync_url, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OSError:
        pytest.fail("Postgres unreachable")
    yield eng
    eng.dispose()
