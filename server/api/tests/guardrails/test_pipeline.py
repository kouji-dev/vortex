"""F1: Guardrail pipeline + Verdict.

Covers:

- Verdict dataclass + helper constructors.
- Pipeline allow / redact / flag / block semantics.
- ``on_match`` override coerces a guardrail's verdict.
- Block raises ``GuardrailBlocked`` carrying offending guardrail name.
- DB-backed: violation row persisted, audit emitted on block.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401 — register Org for FK
import ai_portal.guardrails.model  # noqa: F401 — register tables
from ai_portal.guardrails import (
    GuardrailBlocked,
    GuardrailContext,
    GuardrailPipeline,
    Match,
    PipelineStep,
    Verdict,
    allow,
    block,
    flag,
    redact,
)
from tests.conftest import requires_postgres

# ── fake guardrails ──────────────────────────────────────────────────────


class _AllowAll:
    name = "allow-all"

    async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
        return allow()

    async def check_output(self, response: str, ctx: GuardrailContext) -> Verdict:
        return allow()


class _RedactWord:
    """Replaces 'BAD' with '[REDACTED]' on input."""

    name = "redact-word"

    async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
        if "BAD" not in prompt:
            return allow()
        edited = prompt.replace("BAD", "[REDACTED]")
        return redact(
            matches=[Match(kind="BAD_WORD", start=prompt.find("BAD"), end=prompt.find("BAD") + 3, snippet="BAD")],
            redacted_text=edited,
            reason="bad word",
        )

    async def check_output(self, response: str, ctx: GuardrailContext) -> Verdict:
        return allow()


class _BlockOnTrigger:
    name = "blocker"

    async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
        if "TRIGGER" in prompt:
            return block(matches=[Match(kind="TRIGGER")], reason="triggered")
        return allow()

    async def check_output(self, response: str, ctx: GuardrailContext) -> Verdict:
        return allow()


class _Flagger:
    name = "flagger"

    async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
        if "FLAG" in prompt:
            return flag(matches=[Match(kind="FLAG_WORD")], reason="flag word")
        return allow()

    async def check_output(self, response: str, ctx: GuardrailContext) -> Verdict:
        return allow()


# ── pure tests ──────────────────────────────────────────────────────────


def test_verdict_helpers_build_expected_shapes():
    a = allow("ok")
    assert a.decision == "allow"
    assert a.reason == "ok"

    r = redact(matches=[Match(kind="X")], redacted_text="y", reason="z")
    assert r.decision == "redact"
    assert r.redacted_text == "y"
    assert r.matches[0].kind == "X"

    b = block(matches=[Match(kind="Y")], reason="no")
    assert b.decision == "block"
    assert b.reason == "no"

    f = flag(reason="meh")
    assert f.decision == "flag"


@pytest.mark.asyncio
async def test_pipeline_allow_returns_unchanged_text():
    pipe = GuardrailPipeline.from_guardrails([_AllowAll()])
    res = await pipe.run_input("hello", GuardrailContext())
    assert res.blocked is False
    assert res.text == "hello"
    assert res.violations == []


@pytest.mark.asyncio
async def test_pipeline_redact_replaces_matched_substring():
    pipe = GuardrailPipeline.from_guardrails([_RedactWord()])
    res = await pipe.run_input("this is BAD content", GuardrailContext())
    assert res.text == "this is [REDACTED] content"
    assert len(res.violations) == 1
    name, verdict = res.violations[0]
    assert name == "redact-word"
    assert verdict.decision == "redact"


@pytest.mark.asyncio
async def test_pipeline_block_raises_with_offending_guardrail():
    pipe = GuardrailPipeline.from_guardrails(
        [_AllowAll(), _BlockOnTrigger(), _RedactWord()]
    )
    with pytest.raises(GuardrailBlocked) as exc:
        await pipe.run_input("TRIGGER text", GuardrailContext())
    assert exc.value.guardrail == "blocker"
    assert exc.value.phase == "input"
    assert exc.value.verdict.decision == "block"


@pytest.mark.asyncio
async def test_pipeline_flag_records_violation_but_keeps_going():
    pipe = GuardrailPipeline.from_guardrails([_Flagger(), _AllowAll()])
    res = await pipe.run_input("FLAG please", GuardrailContext())
    assert res.text == "FLAG please"
    assert len(res.violations) == 1
    assert res.violations[0][0] == "flagger"
    assert res.violations[0][1].decision == "flag"


@pytest.mark.asyncio
async def test_pipeline_chains_redacts_then_passes_edited_text():
    """Second guardrail must inspect the redacted text, not the original."""

    seen: list[str] = []

    class _Recorder:
        name = "recorder"

        async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
            seen.append(prompt)
            return allow()

        async def check_output(self, response: str, ctx: GuardrailContext) -> Verdict:
            return allow()

    pipe = GuardrailPipeline.from_guardrails([_RedactWord(), _Recorder()])
    res = await pipe.run_input("hide the BAD now", GuardrailContext())
    assert seen == ["hide the [REDACTED] now"]
    assert res.text == "hide the [REDACTED] now"


@pytest.mark.asyncio
async def test_pipeline_on_match_override_downgrades_block_to_flag():
    """A policy can say 'this guardrail's blocks should only flag'."""

    pipe = GuardrailPipeline(
        [PipelineStep(_BlockOnTrigger(), on_match="flag")]
    )
    res = await pipe.run_input("TRIGGER text", GuardrailContext())
    assert res.blocked is False
    assert len(res.violations) == 1
    assert res.violations[0][1].decision == "block"  # raw verdict preserved


@pytest.mark.asyncio
async def test_pipeline_runs_output_phase():
    """A guardrail that only inspects output is honored."""

    class _OutputBlocker:
        name = "output-blocker"

        async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
            return allow()

        async def check_output(self, response: str, ctx: GuardrailContext) -> Verdict:
            if "leak" in response:
                return block(reason="leak detected")
            return allow()

    pipe = GuardrailPipeline.from_guardrails([_OutputBlocker()])
    with pytest.raises(GuardrailBlocked) as exc:
        await pipe.run_output("model leaked secret", GuardrailContext())
    assert exc.value.phase == "output"


# ── DB-backed tests ─────────────────────────────────────────────────────


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'GR') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


@requires_postgres
def test_service_crud_roundtrip():
    """Policy CRUD: create, get_by_name, list, delete."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.guardrails.service import GuardrailService

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gr-crud")
            svc = GuardrailService(db)
            policy = svc.create(
                org_id=org_id,
                name="strict",
                bundle={"input": [{"name": "secret_scanner", "on_match": "block"}]},
            )
            assert policy.id is not None

            fetched = svc.get_by_name(org_id=org_id, name="strict")
            assert fetched is not None
            assert fetched.bundle_json["input"][0]["name"] == "secret_scanner"

            listed = svc.list_for_org(org_id)
            assert len(listed) == 1

            assert svc.delete(org_id=org_id, policy_id=policy.id) is True
            assert svc.get_by_name(org_id=org_id, name="strict") is None
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_pipeline_block_persists_violation_row():
    """Block must write a guardrail_violations row before raising."""
    import asyncio

    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.guardrails.model import GuardrailViolation

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gr-block")
            request_id = uuid.uuid4().hex[:16]

            pipe = GuardrailPipeline.from_guardrails([_BlockOnTrigger()], db=db)
            ctx = GuardrailContext(
                org_id=str(org_id),
                request_id=request_id,
                actor={"user_id": 1},
            )

            async def _run() -> None:
                with pytest.raises(GuardrailBlocked):
                    await pipe.run_input("please TRIGGER now", ctx)

            asyncio.run(_run())
            db.flush()

            rows = (
                db.query(GuardrailViolation)
                .filter(GuardrailViolation.org_id == org_id)
                .all()
            )
            assert len(rows) == 1
            row = rows[0]
            assert row.guardrail == "blocker"
            assert row.verdict == "block"
            assert row.request_id == request_id
            assert row.evidence_json["reason"] == "triggered"
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_pipeline_redact_persists_violation_with_evidence():
    """Redact records a violation row + emits a webhook (stub allows it)."""
    import asyncio

    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.guardrails.model import GuardrailViolation

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gr-redact")
            pipe = GuardrailPipeline.from_guardrails([_RedactWord()], db=db)
            ctx = GuardrailContext(org_id=str(org_id), request_id="rq-1")

            async def _run() -> Any:
                return await pipe.run_input("BAD here", ctx)

            res = asyncio.run(_run())
            assert res.text == "[REDACTED] here"
            db.flush()

            rows = (
                db.query(GuardrailViolation)
                .filter(GuardrailViolation.org_id == org_id)
                .all()
            )
            assert len(rows) == 1
            assert rows[0].verdict == "redact"
            assert rows[0].evidence_json["matches"][0]["kind"] == "BAD_WORD"
            db.commit()
    finally:
        db.rollback()
        db.close()
