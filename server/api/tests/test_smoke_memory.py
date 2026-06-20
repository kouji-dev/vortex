"""Phase 3 smoke test: pluggable memory subsystem end-to-end.

Boots the FastAPI app against the smoke-mem Postgres DB, runs the
golden path (create / list / recall / uses / delete) plus BYOK
encryption-at-rest. Recall needs a working embedder — the gateway
facade is stubbed with a deterministic SHA-based fake.

Run:
    DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_smoke_mem \
    AUDIT_KEK=lzW_EE_mY6AHkw_W74n-CUjIoXYob9HbI1ww4HDxNoU= \
    MEMORY_KEK=lzW_EE_mY6AHkw_W74n-CUjIoXYob9HbI1ww4HDxNoU= \
    DEPLOYMENT_MODE=saas SECRET_KEY=test-secret-key-32-chars-minimum!! OTEL_ENABLED=false CATALOG_SYNC_ENABLED=false \
    pytest server/api/tests/test_smoke_memory.py
"""
from __future__ import annotations

import hashlib
import os
import uuid as _uuid

import pytest

from tests.conftest import requires_postgres


def _fake_vec(text: str, dim: int = 1536) -> list[float]:
    """Deterministic embedding from sha256 of the text."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    raw = (h * ((dim // len(h)) + 1))[: dim]
    return [(b - 128) / 128.0 for b in raw]


class _FakeEmbeddingsResp:
    """Mimics whatever shape the recaller expects (.data list of vectors)."""

    def __init__(self, vectors: list[list[float]]):
        self.data = vectors
        self.vectors = vectors


async def _fake_gw_embed(texts, *, model, actor):  # signature matches gateway.embed
    return _FakeEmbeddingsResp([_fake_vec(t) for t in texts])


@pytest.fixture
def client(monkeypatch):
    """TestClient with fake embedder patched into the memory recall path."""
    from fastapi.testclient import TestClient
    from ai_portal.main import app
    from ai_portal.memory.recallers import vector_pgvector as vp
    from ai_portal.memory import service as msvc

    # Patch the embedder used by the recaller (gateway.embed import).
    monkeypatch.setattr(vp, "gw_embed", _fake_gw_embed)

    # Patch MemoryService._embedding_provider so persisted memories get
    # a deterministic embedding (vector_search needs Memory.embedding set).
    def _fake_provider():
        async def _embed(text, org_id):
            return _fake_vec(text)
        return _embed

    monkeypatch.setattr(msvc, "_embedding_provider", _fake_provider)

    yield TestClient(app)


# TODO(auth-rework): smoke auth needs real JWT — dev bearer removed in Phase 2
HDR = {"Authorization": "Bearer devtoken"}


def _purge(client) -> None:
    for m in client.get("/v1/memories", headers=HDR).json():
        client.delete(f"/v1/memories/{m['id']}", headers=HDR)


@requires_postgres
def test_smoke_golden_path(client):
    """1-7: create → list → recall → uses → delete → list-empty."""
    if "ai_portal_smoke_mem" not in (os.environ.get("DATABASE_URL") or ""):
        pytest.skip("requires ai_portal_smoke_mem database")
    _purge(client)

    # 2. create
    r = client.post(
        "/v1/memories",
        headers=HDR,
        json={
            "type": "preference",
            "scope_kind": "user",
            "text": "User prefers TypeScript",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    mid = body["id"]
    assert body["text"] == "User prefers TypeScript"

    # 3. list contains the memory
    r = client.get("/v1/memories", headers=HDR)
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert mid in ids

    # 4. recall — fake embedder must surface the memory.
    r = client.post(
        "/v1/memories/recall",
        headers=HDR,
        json={"query": "User prefers TypeScript"},
    )
    assert r.status_code == 200, r.text
    results = r.json()
    assert any(it["memory_id"] == mid for it in results), results

    # 5. uses is empty (no chat turn linked it yet)
    r = client.get(f"/v1/memories/{mid}/uses", headers=HDR)
    assert r.status_code == 200
    assert r.json()["uses"] == []

    # 6. delete
    r = client.delete(f"/v1/memories/{mid}", headers=HDR)
    assert r.status_code == 204

    # 7. list — deleted memory gone
    r = client.get("/v1/memories", headers=HDR)
    assert r.status_code == 200
    assert all(m["id"] != mid for m in r.json())


@requires_postgres
def test_smoke_byok_encryption(client):
    """8. Enable BYOK for org → write memory → raw DB shows `enc:v1:`."""
    if "ai_portal_smoke_mem" not in (os.environ.get("DATABASE_URL") or ""):
        pytest.skip("requires ai_portal_smoke_mem database")
    # MEMORY_KEK must be valid Fernet — clear cache so env is re-read.
    from ai_portal.memory import encryption as enc_mod
    enc_mod._reset_kek_cache()
    assert os.environ.get("MEMORY_KEK"), "MEMORY_KEK must be set"

    _purge(client)

    # Find the dev user's org_id via the legacy /api/users/me/memories shape.
    # Simpler: peek the DB directly via sync engine.
    from sqlalchemy import create_engine, text as _t

    sync_url = os.environ["DATABASE_URL"].replace("+asyncpg", "+psycopg")
    eng = create_engine(sync_url)
    with eng.connect() as conn:
        row = conn.execute(
            _t("SELECT org_id FROM users WHERE email='dev@localhost' LIMIT 1")
        ).fetchone()
        assert row is not None, "dev user not seeded"
        org_id = row[0]

    # Enable BYOK encryption via direct repo call (no admin REST endpoint yet).
    # Use a synchronous run of the async helper.
    import asyncio
    from ai_portal.memory.encryption import MemoryEncryption
    from ai_portal.core.db.session import AsyncSessionLocal

    async def _enable():
        async with AsyncSessionLocal() as session:
            await MemoryEncryption(session).enable(org_id)
            await session.commit()

    asyncio.run(_enable())

    # Write a memory through the HTTP path.
    plain_text = "Likes deep dish pizza"
    r = client.post(
        "/v1/memories",
        headers=HDR,
        json={
            "type": "preference",
            "scope_kind": "user",
            "text": plain_text,
        },
    )
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # Inspect the raw memories.text column — must be ciphertext.
    with eng.connect() as conn:
        raw = conn.execute(
            _t("SELECT text FROM memories WHERE id = :id"),
            {"id": mid},
        ).scalar_one()
    assert raw.startswith("enc:v1:"), f"expected ciphertext, got: {raw!r}"

    # API still returns plaintext (decrypted on read).
    r = client.get("/v1/memories", headers=HDR)
    assert r.status_code == 200
    hit = next((m for m in r.json() if m["id"] == mid), None)
    assert hit is not None
    assert hit["text"] == plain_text

    # Cleanup: disable encryption so subsequent runs don't double-encrypt.
    async def _disable():
        async with AsyncSessionLocal() as session:
            await MemoryEncryption(session).disable(org_id)
            await session.commit()

    asyncio.run(_disable())
