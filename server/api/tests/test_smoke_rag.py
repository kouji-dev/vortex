"""Phase 3 smoke: RAG golden path on `ai_portal_smoke_rag`.

Exercises end-to-end:
  - POST /api/knowledge-bases  → create KB
  - SQL pre-seed Document(status=ready) + DocumentChunk (fake vector + tsvector)
  - POST /api/kbs/{id}/search  → at least one hit
  - POST /api/kbs/{id}/answer  → SSE stream with citation + delta + final

The full upload→ingest pipeline (file readers, embedder, chunker) is bypassed
deliberately — the shortcut documented in the smoke plan: skip ingest, pre-seed
rows directly via SQL with pre-computed embeddings. The embedder and gateway
streamer are stubbed so the test runs offline.

Run:
    DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_smoke_rag \
    AUDIT_KEK=lzW_EE_mY6AHkw_W74n-CUjIoXYob9HbI1ww4HDxNoU= \
    MEMORY_KEK=lzW_EE_mY6AHkw_W74n-CUjIoXYob9HbI1ww4HDxNoU= \
    DEPLOYMENT_MODE=saas SECRET_KEY=test-secret-key-32-chars-minimum!! OTEL_ENABLED=false CATALOG_SYNC_ENABLED=false \
    pytest server/api/tests/test_smoke_rag.py -xvs
"""
from __future__ import annotations

import os
import uuid as _uuid

import pytest
from sqlalchemy import create_engine, text


SMOKE_DB_URL = (
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_smoke_rag"
)


def _smoke_db_available() -> bool:
    try:
        eng = create_engine(SMOKE_DB_URL, pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:  # noqa: BLE001
        return False


requires_smoke_db = pytest.mark.skipif(
    not _smoke_db_available(),
    reason="ai_portal_smoke_rag DB not reachable on :5435",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _smoke_env():
    """Point the process at the smoke DB before importing ai_portal modules."""
    prior = {k: os.environ.get(k) for k in (
        "DATABASE_URL", "AUDIT_KEK", "MEMORY_KEK",
        "DEPLOYMENT_MODE", "SECRET_KEY",
        "OTEL_ENABLED", "CATALOG_SYNC_ENABLED",
    )}
    os.environ["DATABASE_URL"] = SMOKE_DB_URL
    os.environ.setdefault(
        "AUDIT_KEK", "lzW_EE_mY6AHkw_W74n-CUjIoXYob9HbI1ww4HDxNoU="
    )
    os.environ.setdefault(
        "MEMORY_KEK", "lzW_EE_mY6AHkw_W74n-CUjIoXYob9HbI1ww4HDxNoU="
    )
    os.environ.setdefault("DEPLOYMENT_MODE", "saas")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
    os.environ.setdefault("OTEL_ENABLED", "false")
    os.environ.setdefault("CATALOG_SYNC_ENABLED", "false")
    # Force settings cache reset so our DATABASE_URL takes effect.
    try:
        from ai_portal.core.config import get_settings  # type: ignore
        get_settings.cache_clear()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    yield
    for k, v in prior.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="module")
def smoke_engine(_smoke_env):
    eng = create_engine(SMOKE_DB_URL, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        pytest.fail("smoke DB unreachable")
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def seeded(smoke_engine):
    """Create org + user; return (org_id, user_id)."""
    org_id = _uuid.uuid4()
    user_email = f"smoke-rag-{_uuid.uuid4().hex[:8]}@example.com"
    slug = f"smoke-rag-{_uuid.uuid4().hex[:8]}"
    with smoke_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO orgs (id, slug, name, instance_mode, region, status) "
                "VALUES (:id, :slug, :name, false, 'eu-west-1', 'active')"
            ),
            {"id": str(org_id), "slug": slug, "name": "Smoke RAG Org"},
        )
        user_id = conn.execute(
            text(
                "INSERT INTO users (uuid, email, org_id, role, is_active, is_verified) "
                "VALUES (:uuid, :email, :org_id, 'owner', true, true) RETURNING id"
            ),
            {
                "uuid": str(_uuid.uuid4()),
                "email": user_email,
                "org_id": str(org_id),
            },
        ).scalar_one()
    return {"org_id": org_id, "user_id": int(user_id), "email": user_email}


@pytest.fixture(scope="module")
def app_client(seeded):
    """Build a FastAPI app with KB + RAG routers wired and auth overridden."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
    from ai_portal.auth.model import User
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.knowledge_base.router import router as kb_router
    from ai_portal.rag.router import router as rag_router

    db = SessionLocal()
    user = db.get(User, seeded["user_id"])
    assert user is not None, "seed user missing"

    def _get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app = FastAPI()
    app.include_router(kb_router)
    app.include_router(rag_router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_org_id] = lambda: seeded["org_id"]
    app.dependency_overrides[get_db] = _get_db

    yield TestClient(app), db
    app.dependency_overrides.clear()
    db.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@requires_smoke_db
def test_create_kb(app_client):
    client, _ = app_client
    r = client.post("/api/knowledge-bases", json={"name": "Smoke KB"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Smoke KB"
    assert isinstance(body["id"], int)


@pytest.fixture(scope="module")
def seeded_kb_with_chunks(app_client, smoke_engine, seeded):
    """Create KB via HTTP then SQL-seed a ready Document + 2 chunks with vectors+tsv."""
    client, _ = app_client
    r = client.post(
        "/api/knowledge-bases", json={"name": "Smoke KB - pre-seeded"}
    )
    assert r.status_code == 201, r.text
    kb_id = int(r.json()["id"])

    # Fake 1024-dim vector — pgvector accepts a JSON-array literal cast to vector.
    # We use a deterministic non-zero pattern so cosine distance is well-defined.
    vec_a = [0.01] * 1024
    vec_b = [0.02] * 1024
    vec_a[0] = 0.9
    vec_b[1] = 0.9
    vec_a_lit = "[" + ",".join(f"{v:.6f}" for v in vec_a) + "]"
    vec_b_lit = "[" + ",".join(f"{v:.6f}" for v in vec_b) + "]"

    with smoke_engine.begin() as conn:
        doc_id = conn.execute(
            text(
                "INSERT INTO documents (knowledge_base_id, filename, storage_path, status, chunks_total, chunks_done) "
                "VALUES (:kb, :fn, :sp, 'ready', 2, 2) RETURNING id"
            ),
            {"kb": kb_id, "fn": "README.md", "sp": "/dev/null/README.md"},
        ).scalar_one()
        # Chunk A — about RAG retrieval test.
        conn.execute(
            text(
                "INSERT INTO document_chunks (document_id, content, chunk_index, meta, embedding, search_vector) "
                "VALUES (:doc, :content, 0, CAST('{}' AS jsonb), CAST(:emb AS vector), to_tsvector('english', :content))"
            ),
            {
                "doc": doc_id,
                "content": "RAG retrieval test passes when chunks are indexed and searchable.",
                "emb": vec_a_lit,
            },
        )
        # Chunk B — secondary content, also queryable.
        conn.execute(
            text(
                "INSERT INTO document_chunks (document_id, content, chunk_index, meta, embedding, search_vector) "
                "VALUES (:doc, :content, 1, CAST('{}' AS jsonb), CAST(:emb AS vector), to_tsvector('english', :content))"
            ),
            {
                "doc": doc_id,
                "content": "The knowledge base smoke test verifies end to end pipeline.",
                "emb": vec_b_lit,
            },
        )
    return {"kb_id": kb_id, "doc_id": int(doc_id)}


@requires_smoke_db
def test_search_returns_hits(app_client, seeded_kb_with_chunks, monkeypatch):
    client, _ = app_client
    kb_id = seeded_kb_with_chunks["kb_id"]

    # Stub the embedder so dense_search does not hit a real provider.
    fake_qvec = [0.05] * 1024
    fake_qvec[0] = 0.5

    from ai_portal.rag.search import dense as dense_mod
    from ai_portal.rag.search import hybrid as hybrid_mod

    monkeypatch.setattr(dense_mod, "embed_query", lambda _q: fake_qvec)
    monkeypatch.setattr(hybrid_mod, "embed_query", lambda _q: fake_qvec)

    r = client.post(
        f"/api/kbs/{kb_id}/search",
        json={"query": "retrieval test", "top_k": 5, "rerank": False},
    )
    assert r.status_code == 200, r.text
    hits = r.json()["hits"]
    assert len(hits) >= 1, f"expected at least one hit, got {hits}"
    assert hits[0]["kb_id"] == kb_id
    assert hits[0]["text"]
    # Either of our seeded chunks should surface.
    joined = " ".join(h["text"] for h in hits).lower()
    assert "retrieval" in joined or "smoke" in joined or "knowledge base" in joined


@requires_smoke_db
def test_answer_streams_sse_with_citation(
    app_client, seeded_kb_with_chunks, monkeypatch
):
    client, _ = app_client
    kb_id = seeded_kb_with_chunks["kb_id"]

    from ai_portal.rag.answer import service as answer_svc
    from ai_portal.rag.search import dense as dense_mod
    from ai_portal.rag.search import hybrid as hybrid_mod

    fake_qvec = [0.05] * 1024
    fake_qvec[0] = 0.5
    monkeypatch.setattr(dense_mod, "embed_query", lambda _q: fake_qvec)
    monkeypatch.setattr(hybrid_mod, "embed_query", lambda _q: fake_qvec)

    # Fake gateway-LLM stream: yields two text chunks. The answer service will
    # inject citation markers and surface a `final` event.
    def fake_stream(system, user, opts):
        yield "Based on the indexed chunks, "
        yield "the smoke test pipeline works."

    monkeypatch.setattr(answer_svc, "_default_stream", fake_stream)

    # Disable rewrite (multi-turn) so it does not try to call a real LLM.
    from ai_portal.rag.answer import rewrite as rewrite_mod

    monkeypatch.setattr(
        rewrite_mod, "rewrite_question", lambda q, turns, **kw: q
    )

    r = client.post(
        f"/api/kbs/{kb_id}/answer",
        json={
            "query": "what does the smoke test verify",
            "top_k": 5,
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    raw = r.text
    assert "event: citation" in raw, raw[:400]
    assert "event: delta" in raw, raw[:400]
    assert "event: final" in raw, raw[:400]
    assert "event: done" in raw, raw[:400]
