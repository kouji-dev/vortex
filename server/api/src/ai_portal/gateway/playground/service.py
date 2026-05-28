"""Playground service — session CRUD + multi-model run dispatch.

Two responsibilities:

1. **Session CRUD** — :meth:`PlaygroundService.list_sessions`,
   :meth:`PlaygroundService.create_session` (upsert by name+user), and
   :meth:`PlaygroundService.get_session`. Snapshots are org-scoped and,
   when ``user_id`` is set on create, user-scoped too.
2. **Run dispatch** — :meth:`PlaygroundService.run_snapshot` translates a
   snapshot into one or more :class:`LLMRequest` calls and fans them out
   through the gateway facade. Each model's result captures the response
   text, token usage, cost, latency, and any error.

The service does not own routing or provider selection — it always calls
:func:`ai_portal.gateway.facade.complete` which goes through the
process-wide default facade. Tests stub that out via
``set_default_facade``.
"""

from __future__ import annotations

import asyncio
import time
import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.gateway import facade as gateway_facade
from ai_portal.gateway.facade import Actor as FacadeActor
from ai_portal.gateway.playground.model import PlaygroundSession
from ai_portal.gateway.playground.schemas import RunResult
from ai_portal.gateway.types import LLMRequest, Message, TextBlock


@dataclass(frozen=True)
class SessionView:
    """Service-layer view of a saved playground session."""

    id: _uuid.UUID
    name: str
    snapshot: dict
    created_at: object
    updated_at: object


def _row_to_view(row: PlaygroundSession) -> SessionView:
    return SessionView(
        id=row.id,
        name=row.name or "",
        snapshot=dict(row.snapshot_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PlaygroundService:
    """CRUD + run orchestrator. Stateless apart from the SQLAlchemy session."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── CRUD ─────────────────────────────────────────────────────────────

    def list_sessions(
        self, *, org_id: _uuid.UUID, user_id: int | None = None
    ) -> list[SessionView]:
        q = select(PlaygroundSession).where(PlaygroundSession.org_id == org_id)
        if user_id is not None:
            q = q.where(PlaygroundSession.user_id == user_id)
        q = q.order_by(PlaygroundSession.updated_at.desc())
        return [_row_to_view(r) for r in self.db.scalars(q)]

    def create_session(
        self,
        *,
        org_id: _uuid.UUID,
        user_id: int | None,
        name: str,
        snapshot: dict,
    ) -> SessionView:
        """Insert a new snapshot row. Returns the persisted view."""
        row = PlaygroundSession(
            org_id=org_id,
            user_id=user_id,
            name=name or "",
            snapshot_json=dict(snapshot or {}),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _row_to_view(row)

    def get_session(
        self, *, org_id: _uuid.UUID, session_id: _uuid.UUID
    ) -> SessionView | None:
        row = self.db.get(PlaygroundSession, session_id)
        if row is None or row.org_id != org_id:
            return None
        return _row_to_view(row)

    def delete_session(self, *, org_id: _uuid.UUID, session_id: _uuid.UUID) -> bool:
        row = self.db.get(PlaygroundSession, session_id)
        if row is None or row.org_id != org_id:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # ── run dispatch ─────────────────────────────────────────────────────

    @staticmethod
    def _models_from_snapshot(snapshot: dict) -> list[str]:
        models = snapshot.get("models")
        if isinstance(models, list) and models:
            return [str(m) for m in models if m]
        single = snapshot.get("model")
        if single:
            return [str(single)]
        return []

    @staticmethod
    def _build_request(model: str, snapshot: dict) -> LLMRequest:
        """Translate a snapshot into a canonical :class:`LLMRequest`."""
        messages: list[Message] = []
        system = (snapshot.get("system") or "").strip()
        if system:
            messages.append(Message(role="system", content=[TextBlock(text=system)]))
        prompt = snapshot.get("prompt") or ""
        messages.append(Message(role="user", content=[TextBlock(text=str(prompt))]))
        temperature = snapshot.get("temperature")
        max_tokens = snapshot.get("max_tokens")
        return LLMRequest(
            model=model,
            messages=messages,
            temperature=(float(temperature) if temperature is not None else None),
            max_tokens=int(max_tokens) if max_tokens else None,
        )

    @staticmethod
    def _response_text(resp_content: Sequence) -> str:
        parts: list[str] = []
        for block in resp_content:
            txt = getattr(block, "text", None)
            if txt:
                parts.append(txt)
        return "".join(parts)

    async def _run_one(
        self,
        *,
        model: str,
        snapshot: dict,
        actor: FacadeActor,
    ) -> RunResult:
        req = self._build_request(model, snapshot)
        started = time.monotonic()
        try:
            resp = await gateway_facade.complete(req, actor)
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - started) * 1000)
            return RunResult(model=model, latency_ms=latency_ms, error=str(exc))
        latency_ms = int((time.monotonic() - started) * 1000)
        # Cost is best-effort: prefer pricing-resolved value from the
        # facade trace path, but the response itself doesn't carry it —
        # we recompute from usage + the default facade pricing hook.
        pricing = gateway_facade.get_default_facade().cfg.resolve_pricing(model)
        if pricing is not None:
            from ai_portal.gateway.pricing import compute_cost_cents  # noqa: PLC0415

            cost = compute_cost_cents(resp.usage, pricing)
        else:
            cost = 0.0
        return RunResult(
            model=resp.model_used or model,
            output=self._response_text(resp.content),
            latency_ms=latency_ms,
            cost_cents=float(cost),
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
        )

    async def run_snapshot(
        self,
        *,
        org_id: _uuid.UUID,
        user_id: int | None,
        snapshot: dict,
    ) -> list[RunResult]:
        """Fan out one snapshot to N models via the gateway facade.

        Returns one :class:`RunResult` per model in input order.
        """
        models = self._models_from_snapshot(snapshot)
        if not models:
            return []
        actor = FacadeActor(
            org_id=org_id,
            user_id=user_id,
            kind="user" if user_id is not None else "service",
        )
        coros = [self._run_one(model=m, snapshot=snapshot, actor=actor) for m in models]
        return await asyncio.gather(*coros)


__all__ = ["PlaygroundService", "SessionView"]
