"""Service layer for gateway traces — search + get + replay.

Three responsibilities:

1. :meth:`TracesService.search` — paginated org-scoped query with optional
   filters (``model_used``, ``status``, ``actor_user_id``, ``provider``,
   time range). Cursor is a base64 of ``ts.isoformat()|id`` — keyset
   pagination that survives concurrent inserts.
2. :meth:`TracesService.get` — single row, org-scoped.
3. :meth:`TracesService.replay` — rebuild the canonical
   :class:`LLMRequest` from the stored ``request_json``, optionally swap
   model / routing policy, dispatch through the supplied provider, write a
   new trace row, return its id.

The router lives in :mod:`gateway.traces.router`; the service is HTTP-free
so other modules (and unit tests) can use it directly.
"""

from __future__ import annotations

import base64
import time
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ai_portal.gateway.traces.model import RequestTrace
from ai_portal.gateway.traces.writer import TraceRecord, _write_rows_sync
from ai_portal.gateway.types import LLMRequest, LLMResponse

# ── DTOs ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TraceSummary:
    """Row shape used in search results."""

    id: _uuid.UUID
    org_id: _uuid.UUID
    actor_json: dict
    route: str
    model_requested: str | None
    model_used: str | None
    provider: str | None
    status: str
    latency_ms: int | None
    ttft_ms: int | None
    tokens_in: int
    tokens_out: int
    tokens_cache_read: int
    tokens_cache_write: int
    cost_cents: float
    cache_hit: bool
    error: str | None
    request_hash: str | None
    ts: datetime

    @classmethod
    def from_row(cls, row: RequestTrace) -> TraceSummary:
        return cls(
            id=row.id,
            org_id=row.org_id,
            actor_json=dict(row.actor_json or {}),
            route=row.route,
            model_requested=row.model_requested,
            model_used=row.model_used,
            provider=row.provider,
            status=row.status,
            latency_ms=row.latency_ms,
            ttft_ms=row.ttft_ms,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            tokens_cache_read=row.tokens_cache_read,
            tokens_cache_write=row.tokens_cache_write,
            cost_cents=float(row.cost_cents),
            cache_hit=row.cache_hit,
            error=row.error,
            request_hash=row.request_hash,
            ts=row.ts,
        )


@dataclass(frozen=True)
class TraceDetail:
    """Full row including ``request_json``."""

    summary: TraceSummary
    request_json: dict | None


@dataclass(frozen=True)
class SearchPage:
    items: list[TraceSummary]
    next_cursor: str | None


# ── cursor helpers ───────────────────────────────────────────────────────


def _encode_cursor(ts: datetime, trace_id: _uuid.UUID) -> str:
    raw = f"{ts.isoformat()}|{trace_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, _uuid.UUID] | None:
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + pad).encode()).decode()
        ts_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), _uuid.UUID(id_str)
    except (ValueError, TypeError):
        return None


# ── service ──────────────────────────────────────────────────────────────


class TracesService:
    """Persistence + replay orchestrator for ``request_traces``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def search(
        self,
        *,
        org_id: _uuid.UUID,
        model: str | None = None,
        status: str | None = None,
        provider: str | None = None,
        actor_user_id: int | None = None,
        ts_from: datetime | None = None,
        ts_to: datetime | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> SearchPage:
        """Paginated keyset search ordered by ``(ts DESC, id DESC)``."""
        limit = max(1, min(limit, 200))

        q = select(RequestTrace).where(RequestTrace.org_id == org_id)
        if model:
            q = q.where(RequestTrace.model_used == model)
        if status:
            q = q.where(RequestTrace.status == status)
        if provider:
            q = q.where(RequestTrace.provider == provider)
        if actor_user_id is not None:
            q = q.where(
                RequestTrace.actor_json["actor_user_id"].astext == str(actor_user_id)
            )
        if ts_from is not None:
            q = q.where(RequestTrace.ts >= ts_from)
        if ts_to is not None:
            q = q.where(RequestTrace.ts <= ts_to)

        if cursor:
            decoded = _decode_cursor(cursor)
            if decoded is not None:
                cur_ts, cur_id = decoded
                q = q.where(
                    (RequestTrace.ts < cur_ts)
                    | ((RequestTrace.ts == cur_ts) & (RequestTrace.id < cur_id))
                )

        q = q.order_by(desc(RequestTrace.ts), desc(RequestTrace.id)).limit(limit + 1)
        rows = list(self.db.scalars(q))
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [TraceSummary.from_row(r) for r in rows]
        next_cursor = (
            _encode_cursor(rows[-1].ts, rows[-1].id) if has_more and rows else None
        )
        return SearchPage(items=items, next_cursor=next_cursor)

    def get(self, *, org_id: _uuid.UUID, trace_id: _uuid.UUID) -> TraceDetail | None:
        q = select(RequestTrace).where(
            RequestTrace.id == trace_id, RequestTrace.org_id == org_id
        )
        row = self.db.scalar(q)
        if row is None:
            return None
        return TraceDetail(
            summary=TraceSummary.from_row(row),
            request_json=dict(row.request_json) if row.request_json else None,
        )

    async def replay(
        self,
        *,
        org_id: _uuid.UUID,
        trace_id: _uuid.UUID,
        provider: Any,
        model_override: str | None = None,
        routing_policy_id_override: str | None = None,
        actor_json: dict | None = None,
    ) -> _uuid.UUID | None:
        """Re-dispatch the historic request through ``provider``.

        Writes a new trace row. Returns the new trace id, or ``None`` if the
        original trace doesn't exist / lacks a stored request body.
        """
        detail = self.get(org_id=org_id, trace_id=trace_id)
        if detail is None or detail.request_json is None:
            return None

        req_data = dict(detail.request_json)
        if model_override:
            req_data["model"] = model_override
        # Stash the policy override on metadata so downstream routing logic
        # (phase C) can pick it up. Replay doesn't know about routing
        # internals — it just records intent.
        meta = dict(req_data.get("metadata") or {})
        if routing_policy_id_override:
            meta["routing_policy_id"] = routing_policy_id_override
        meta["replay_of"] = str(trace_id)
        req_data["metadata"] = meta

        try:
            req = LLMRequest.model_validate(req_data)
        except Exception:  # noqa: BLE001
            # Bad stored request — treat as missing.
            return None

        started = time.monotonic()
        resp: LLMResponse | None = None
        status = "ok"
        error: str | None = None
        try:
            resp = await provider.complete_canonical(req)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = str(exc)

        latency_ms = int((time.monotonic() - started) * 1000)

        new_id = _uuid.uuid4()
        record = TraceRecord(
            id=new_id,
            org_id=org_id,
            route=detail.summary.route,
            actor_json=dict(actor_json or detail.summary.actor_json or {}),
            model_requested=req.model,
            model_used=resp.model_used if resp else req.model,
            provider=resp.provider if resp else None,
            status=status,
            latency_ms=latency_ms,
            tokens_in=resp.usage.input_tokens if resp else 0,
            tokens_out=resp.usage.output_tokens if resp else 0,
            tokens_cache_read=resp.usage.cache_read_tokens if resp else 0,
            tokens_cache_write=resp.usage.cache_write_tokens if resp else 0,
            cost_cents=0.0,
            cache_hit=False,
            error=error,
            request_json=req.model_dump(mode="json"),
        )
        # Synchronous write — replay is interactive, the caller wants the
        # new row visible by the time the HTTP response returns.
        _write_rows_sync([record])
        return new_id


__all__ = [
    "SearchPage",
    "TraceDetail",
    "TraceSummary",
    "TracesService",
]
