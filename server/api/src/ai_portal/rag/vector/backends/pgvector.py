"""pgvector backend (default).

Persists points in the ``kb_chunk_embeddings`` table created in alembic
revision ``057_rag_management``. Reads use pgvector ``<=>`` cosine
distance ordering.

Backend implementation is sync-friendly; the protocol expects async
methods, so we wrap blocking SQL calls in ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_portal.rag.vector.protocol import (
    VectorFilter,
    VectorHit,
    VectorPoint,
)


def _vec_literal(vec: list[float]) -> str:
    """pgvector text format: ``'[1.0,2.0,...]'``."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _build_where(flt: VectorFilter | None) -> tuple[str, dict]:
    """Translate filter to SQL WHERE fragment + bound params."""
    clauses: list[str] = []
    params: dict = {}
    if not flt or flt.is_empty():
        return "", params
    if flt.must:
        for i, (k, v) in enumerate(flt.must.items()):
            pname = f"must_{i}"
            clauses.append(f"meta_json ->> '{k}' = :{pname}")
            params[pname] = str(v)
    if flt.must_not:
        for i, (k, v) in enumerate(flt.must_not.items()):
            pname = f"mn_{i}"
            clauses.append(
                f"(meta_json ->> '{k}' IS NULL OR meta_json ->> '{k}' <> :{pname})"
            )
            params[pname] = str(v)
    if flt.range:
        for i, (k, spec) in enumerate(flt.range.items()):
            for op_name, op_sql in (
                ("gte", ">="),
                ("gt", ">"),
                ("lte", "<="),
                ("lt", "<"),
            ):
                if op_name in spec:
                    pname = f"rng_{i}_{op_name}"
                    clauses.append(
                        f"(meta_json ->> '{k}')::numeric {op_sql} :{pname}"
                    )
                    params[pname] = spec[op_name]
    where = " AND ".join(clauses)
    return where, params


@dataclass
class PgVectorStore:
    """Session-aware pgvector wrapper.

    The session is injected via :meth:`bind`; construction (via the registry
    factory) returns an unbound store. Callers bind a request-scoped
    session before issuing operations.
    """

    name: str = "pgvector"
    session: Session | None = None
    table: str = "kb_chunk_embeddings"

    def bind(self, session: Session) -> "PgVectorStore":
        self.session = session
        return self

    def _db(self) -> Session:
        if self.session is None:
            raise RuntimeError("PgVectorStore not bound to a session — call .bind(db)")
        return self.session

    async def ensure_namespace(self, ns: str, dim: int) -> None:
        # No-op: the column is a shared ``vector(1536)``; the namespace
        # discriminator is ``kb_chunk_embeddings.namespace``. Dim mismatch
        # is rejected at upsert time.
        return None

    async def upsert(self, ns: str, points: list[VectorPoint]) -> None:
        if not points:
            return

        def _do() -> None:
            db = self._db()
            for p in points:
                meta = json.dumps(p.payload or {})
                acl = json.dumps((p.payload or {}).get("acl", {}))
                kb_id = (p.payload or {}).get("kb_id")
                vec = _vec_literal(p.embedding)
                db.execute(
                    text(
                        f"""
                        INSERT INTO {self.table}
                            (chunk_id, kb_id, namespace, dim, embedding, meta_json, acl_json)
                        VALUES
                            (:cid, :kb, :ns, :dim, (:vec)::vector, (:meta)::jsonb, (:acl)::jsonb)
                        ON CONFLICT (chunk_id) DO UPDATE
                            SET embedding = EXCLUDED.embedding,
                                namespace = EXCLUDED.namespace,
                                dim = EXCLUDED.dim,
                                meta_json = EXCLUDED.meta_json,
                                acl_json = EXCLUDED.acl_json
                        """
                    ),
                    {
                        "cid": p.id,
                        "kb": kb_id,
                        "ns": ns,
                        "dim": len(p.embedding),
                        "vec": vec,
                        "meta": meta,
                        "acl": acl,
                    },
                )
            db.commit()

        await asyncio.to_thread(_do)

    async def delete(self, ns: str, ids: list[str]) -> None:
        if not ids:
            return

        def _do() -> None:
            db = self._db()
            db.execute(
                text(
                    f"DELETE FROM {self.table} WHERE namespace = :ns AND chunk_id = ANY(:ids)"
                ),
                {"ns": ns, "ids": list(ids)},
            )
            db.commit()

        await asyncio.to_thread(_do)

    async def query(
        self,
        ns: str,
        vec: list[float],
        top_k: int,
        flt: VectorFilter | None = None,
    ) -> list[VectorHit]:
        where_clause, params = _build_where(flt)
        where_sql = f" AND {where_clause}" if where_clause else ""

        def _do() -> list[VectorHit]:
            db = self._db()
            params.update({"ns": ns, "vec": _vec_literal(vec), "limit": top_k})
            rows = db.execute(
                text(
                    f"""
                    SELECT chunk_id, meta_json,
                           1.0 - (embedding <=> (:vec)::vector) AS score
                    FROM {self.table}
                    WHERE namespace = :ns{where_sql}
                    ORDER BY embedding <=> (:vec)::vector
                    LIMIT :limit
                    """
                ),
                params,
            ).fetchall()
            return [
                VectorHit(
                    id=str(r[0]),
                    score=float(r[2]) if r[2] is not None else 0.0,
                    payload=r[1] or {},
                )
                for r in rows
            ]

        return await asyncio.to_thread(_do)

    async def count(self, ns: str, flt: VectorFilter | None = None) -> int:
        where_clause, params = _build_where(flt)
        where_sql = f" AND {where_clause}" if where_clause else ""

        def _do() -> int:
            db = self._db()
            params["ns"] = ns
            row = db.execute(
                text(
                    f"SELECT COUNT(*) FROM {self.table} WHERE namespace = :ns{where_sql}"
                ),
                params,
            ).first()
            return int(row[0]) if row else 0

        return await asyncio.to_thread(_do)


def build(config: dict) -> PgVectorStore:
    return PgVectorStore(table=config.get("table", "kb_chunk_embeddings"))
