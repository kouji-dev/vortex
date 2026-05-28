"""Guardrail pipeline + persistence.

:class:`GuardrailPipeline` runs an ordered list of guardrails on one piece
of text (a prompt or a response), applies the verdicts, and records any
non-``allow`` outcomes to ``guardrail_violations``.

Pipeline rules:

- **allow**  → continue with current text, no record.
- **redact** → swap in ``verdict.redacted_text``, record a violation,
  continue.
- **flag**   → record a violation, continue with current text.
- **block**  → record a violation, raise :class:`GuardrailBlocked`.

The pipeline accepts a list of ``(guardrail, on_match)`` pairs so a policy
can say "secret scanner is fatal, PII is just a redact". When ``on_match``
is set, it overrides the verdict's own ``decision`` for any non-allow
result. This lets one guardrail be reused under different actions across
policies.

Audit + webhook fan-out:

- Every non-allow verdict calls ``emit_audit`` with ``guardrail.violation``
  event and a payload that includes the offending text snippets.
- ``emit_webhook`` is invoked for ``guardrail.blocked`` and
  ``guardrail.redacted`` so external systems can be notified.

``GuardrailService`` is the thin CRUD layer for the
:class:`~ai_portal.guardrails.model.GuardrailPolicy` table.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.control_plane import emit_audit, emit_webhook
from ai_portal.guardrails.model import GuardrailPolicy, GuardrailViolation
from ai_portal.guardrails.protocol import (
    Decision,
    Guardrail,
    GuardrailBlocked,
    GuardrailContext,
    Verdict,
)

logger = logging.getLogger(__name__)


# ── pipeline ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PipelineStep:
    """One guardrail in a pipeline, optionally with an action override.

    ``on_match`` (``redact``/``block``/``flag``) overrides the guardrail's
    own verdict for any non-allow result. ``None`` means "use the
    guardrail's decision as-is".
    """

    guardrail: Guardrail
    on_match: Decision | None = None


@dataclass
class PipelineResult:
    """What the pipeline returns to the caller.

    ``text`` is the (possibly redacted) text after every guardrail ran.
    ``violations`` is the list of non-allow verdicts in the order they
    fired. ``blocked`` is True iff one of the guardrails returned block —
    in which case :class:`GuardrailBlocked` was also raised; the result
    object is available on the exception for inspection.
    """

    text: str
    violations: list[tuple[str, Verdict]] = field(default_factory=list)
    blocked: bool = False


def _coerce_decision(
    verdict: Verdict, on_match: Decision | None
) -> Decision:
    """Apply ``on_match`` override for non-allow verdicts."""
    if verdict.decision == "allow":
        return "allow"
    if on_match is None:
        return verdict.decision
    return on_match


def _violation_row(
    *,
    org_id: _uuid.UUID | None,
    request_id: str | None,
    guardrail_name: str,
    decision: Decision,
    verdict: Verdict,
) -> dict[str, Any]:
    """Build the canonical evidence payload (dict + DB row)."""
    return {
        "guardrail": guardrail_name,
        "verdict": decision,
        "reason": verdict.reason,
        "matches": [
            {
                "kind": m.kind,
                "start": m.start,
                "end": m.end,
                "snippet": m.snippet,
                "score": m.score,
                "extra": dict(m.extra),
            }
            for m in verdict.matches
        ],
        "org_id": str(org_id) if org_id else None,
        "request_id": request_id,
    }


class GuardrailPipeline:
    """Runs a bundle of guardrails on one direction (input or output).

    :param steps: ordered list of :class:`PipelineStep`.
    :param db: optional Session. When provided, violations are persisted
        to ``guardrail_violations`` and audit events are emitted.
    """

    def __init__(
        self,
        steps: Sequence[PipelineStep],
        *,
        db: Session | None = None,
    ) -> None:
        self._steps = list(steps)
        self._db = db

    @classmethod
    def from_guardrails(
        cls,
        guardrails: Iterable[Guardrail],
        *,
        db: Session | None = None,
    ) -> GuardrailPipeline:
        return cls([PipelineStep(g) for g in guardrails], db=db)

    async def run_input(
        self, text: str, ctx: GuardrailContext
    ) -> PipelineResult:
        return await self._run(text, ctx, phase="input")

    async def run_output(
        self, text: str, ctx: GuardrailContext
    ) -> PipelineResult:
        return await self._run(text, ctx, phase="output")

    async def _run(
        self,
        text: str,
        ctx: GuardrailContext,
        *,
        phase: str,
    ) -> PipelineResult:
        current = text
        result = PipelineResult(text=current)

        for step in self._steps:
            verdict = await self._invoke(step.guardrail, current, ctx, phase)
            decision = _coerce_decision(verdict, step.on_match)

            if decision == "allow":
                continue

            result.violations.append((step.guardrail.name, verdict))
            self._record(
                ctx=ctx,
                guardrail_name=step.guardrail.name,
                decision=decision,
                verdict=verdict,
            )

            if decision == "redact":
                if verdict.redacted_text is not None:
                    current = verdict.redacted_text
                    result.text = current
                continue
            if decision == "flag":
                continue
            if decision == "block":
                result.blocked = True
                result.text = current
                raise GuardrailBlocked(
                    guardrail=step.guardrail.name,
                    verdict=verdict,
                    phase=phase,  # type: ignore[arg-type]
                )

        result.text = current
        return result

    @staticmethod
    async def _invoke(
        guardrail: Guardrail,
        text: str,
        ctx: GuardrailContext,
        phase: str,
    ) -> Verdict:
        if phase == "input":
            return await guardrail.check_input(text, ctx)
        return await guardrail.check_output(text, ctx)

    def _record(
        self,
        *,
        ctx: GuardrailContext,
        guardrail_name: str,
        decision: Decision,
        verdict: Verdict,
    ) -> None:
        org_uuid = _parse_org(ctx.org_id)
        evidence = _violation_row(
            org_id=org_uuid,
            request_id=ctx.request_id,
            guardrail_name=guardrail_name,
            decision=decision,
            verdict=verdict,
        )

        if self._db is not None and org_uuid is not None:
            try:
                row = GuardrailViolation(
                    org_id=org_uuid,
                    request_id=ctx.request_id,
                    guardrail=guardrail_name,
                    verdict=decision,
                    evidence_json=evidence,
                )
                self._db.add(row)
                self._db.flush()
            except Exception:  # pragma: no cover - DB failure should not break pipeline
                logger.exception("guardrails: failed to persist violation")

        # Audit every non-allow outcome.
        if org_uuid is not None:
            try:
                emit_audit(
                    org_id=org_uuid,
                    event_type="guardrail.violation",
                    actor=ctx.actor or {},
                    resource={"type": "guardrail", "id": guardrail_name},
                    payload=evidence,
                    request_id=ctx.request_id,
                )
            except Exception:  # pragma: no cover
                logger.exception("guardrails: emit_audit failed")

            try:
                event_type = {
                    "block": "guardrail.blocked",
                    "redact": "guardrail.redacted",
                    "flag": "guardrail.flagged",
                }.get(decision, "guardrail.violation")
                emit_webhook(event_type, evidence, org_uuid)
            except Exception:  # pragma: no cover
                logger.exception("guardrails: emit_webhook failed")


def _parse_org(val: str | _uuid.UUID | None) -> _uuid.UUID | None:
    if val is None:
        return None
    if isinstance(val, _uuid.UUID):
        return val
    try:
        return _uuid.UUID(str(val))
    except (TypeError, ValueError):
        return None


# ── service (policy CRUD) ───────────────────────────────────────────────


class GuardrailService:
    """Persistence facade for :class:`GuardrailPolicy`."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        org_id: _uuid.UUID,
        name: str,
        bundle: dict[str, Any],
    ) -> GuardrailPolicy:
        policy = GuardrailPolicy(
            org_id=org_id,
            name=name,
            bundle_json=dict(bundle or {}),
        )
        self.db.add(policy)
        self.db.commit()
        self.db.refresh(policy)
        return policy

    def get(
        self, *, org_id: _uuid.UUID, policy_id: _uuid.UUID
    ) -> GuardrailPolicy | None:
        policy = self.db.get(GuardrailPolicy, policy_id)
        if policy is None or policy.org_id != org_id:
            return None
        return policy

    def get_by_name(
        self, *, org_id: _uuid.UUID, name: str
    ) -> GuardrailPolicy | None:
        return self.db.scalars(
            select(GuardrailPolicy)
            .where(GuardrailPolicy.org_id == org_id)
            .where(GuardrailPolicy.name == name)
        ).first()

    def list_for_org(self, org_id: _uuid.UUID) -> list[GuardrailPolicy]:
        return list(
            self.db.scalars(
                select(GuardrailPolicy)
                .where(GuardrailPolicy.org_id == org_id)
                .order_by(GuardrailPolicy.created_at.desc())
            )
        )

    def delete(self, *, org_id: _uuid.UUID, policy_id: _uuid.UUID) -> bool:
        policy = self.db.get(GuardrailPolicy, policy_id)
        if policy is None or policy.org_id != org_id:
            return False
        self.db.delete(policy)
        self.db.commit()
        return True


__all__ = [
    "GuardrailPipeline",
    "GuardrailService",
    "PipelineResult",
    "PipelineStep",
]
