"""Guardrail policy + live-test HTTP surface (J6).

Endpoints:

- ``GET    /api/v1/gateway/guardrail-policies`` — list this org's policies
- ``POST   /api/v1/gateway/guardrail-policies`` — create one
- ``PUT    /api/v1/gateway/guardrail-policies/{id}`` — replace bundle / name
- ``DELETE /api/v1/gateway/guardrail-policies/{id}`` — remove one
- ``POST   /api/v1/gateway/guardrail-policies/test`` — live test, no persist

Live-test does **not** persist anything. It validates the bundle, runs
each step's logic against the supplied prompt, and returns the per-step
verdict trace plus a strongest-wins final decision. This is the same
shape the frontend's TestPane renders.
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_permission
from ai_portal.guardrails.policy_validators import (
    ACTION_PRIORITY,
    normalize_bundle,
    resolve_final_decision,
    validate_bundle,
)
from ai_portal.guardrails.service import GuardrailService
from ai_portal.rbac.service import Actor

router = APIRouter(
    prefix="/api/v1/gateway/guardrail-policies",
    tags=["gateway-guardrail-policies"],
)


# ── schemas ──────────────────────────────────────────────────────────────


class GuardrailStepDTO(BaseModel):
    kind: str
    config: dict = Field(default_factory=dict)
    on_match: str = "allow"


class GuardrailBundleDTO(BaseModel):
    input: list[GuardrailStepDTO] = Field(default_factory=list)
    output: list[GuardrailStepDTO] = Field(default_factory=list)


class PolicyCreate(BaseModel):
    name: str
    bundle: GuardrailBundleDTO


class PolicyOut(BaseModel):
    id: str
    name: str
    bundle: GuardrailBundleDTO


class GuardrailMatchOut(BaseModel):
    kind: str
    span: tuple[int, int] | None = None
    evidence: str | None = None


class GuardrailVerdictOut(BaseModel):
    guardrail: str
    decision: str
    matches: list[GuardrailMatchOut] = Field(default_factory=list)
    redacted_text: str | None = None
    reason: str = ""


class TestRequest(BaseModel):
    prompt: str
    bundle: GuardrailBundleDTO


class TestResponse(BaseModel):
    prompt: str
    verdicts: list[GuardrailVerdictOut]
    final_decision: str


# ── helpers ──────────────────────────────────────────────────────────────


def _bundle_to_dict(bundle: GuardrailBundleDTO) -> dict:
    return {
        "input": [s.model_dump() for s in bundle.input],
        "output": [s.model_dump() for s in bundle.output],
    }


def _enforce_valid_bundle(bundle_dict: dict) -> None:
    errs = validate_bundle(bundle_dict)
    if errs:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "invalid guardrail bundle",
                "errors": [{"path": e.path, "message": e.message} for e in errs],
            },
        )


def _policy_out(row) -> PolicyOut:
    raw = row.bundle_json or {}
    return PolicyOut(
        id=str(row.id),
        name=row.name,
        bundle=GuardrailBundleDTO(
            **{k: raw.get(k, []) for k in ("input", "output")}
        ),
    )


# ── CRUD ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[PolicyOut])
def list_policies(
    actor: Actor = Depends(require_permission("gateway:guardrails:read")),
    db: Session = Depends(get_db),
) -> list[PolicyOut]:
    svc = GuardrailService(db)
    return [_policy_out(p) for p in svc.list_for_org(actor.org_id)]


@router.post("", response_model=PolicyOut, status_code=201)
def create_policy(
    body: PolicyCreate,
    actor: Actor = Depends(require_permission("gateway:guardrails:write")),
    db: Session = Depends(get_db),
) -> PolicyOut:
    bundle_dict = _bundle_to_dict(body.bundle)
    _enforce_valid_bundle(bundle_dict)
    svc = GuardrailService(db)
    row = svc.create(
        org_id=actor.org_id,
        name=body.name,
        bundle=normalize_bundle(bundle_dict),
    )
    return _policy_out(row)


@router.put("/{policy_id}", response_model=PolicyOut)
def update_policy(
    policy_id: _uuid.UUID,
    body: PolicyCreate,
    actor: Actor = Depends(require_permission("gateway:guardrails:write")),
    db: Session = Depends(get_db),
) -> PolicyOut:
    bundle_dict = _bundle_to_dict(body.bundle)
    _enforce_valid_bundle(bundle_dict)
    svc = GuardrailService(db)
    row = svc.get(org_id=actor.org_id, policy_id=policy_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="policy not found")
    row.name = body.name
    row.bundle_json = normalize_bundle(bundle_dict)
    db.commit()
    db.refresh(row)
    return _policy_out(row)


@router.delete("/{policy_id}", status_code=204)
def delete_policy(
    policy_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("gateway:guardrails:write")),
    db: Session = Depends(get_db),
) -> None:
    svc = GuardrailService(db)
    ok = svc.delete(org_id=actor.org_id, policy_id=policy_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="policy not found")


# ── live test ────────────────────────────────────────────────────────────


@router.post("/test", response_model=TestResponse)
async def test_policy(
    body: TestRequest,
    actor: Actor = Depends(require_permission("gateway:guardrails:read")),
) -> TestResponse:
    """Run the bundle against ``prompt`` without persisting anything.

    Each step contributes one verdict. ``final_decision`` is the strongest
    action across all verdicts (block > redact > flag > allow).

    Steps return ``allow`` by default; live-test is heuristics-only — it
    doesn't call any network providers (OpenAI moderation, LlamaGuard,
    custom classifiers). Pure-heuristic steps (``regex``,
    ``prompt_injection_classifier`` w/o classifier, ``secret_scanner``,
    etc.) return real verdicts. This keeps live-test cheap, deterministic,
    and offline-safe for the editor preview pane.
    """
    bundle_dict = _bundle_to_dict(body.bundle)
    _enforce_valid_bundle(bundle_dict)

    verdicts: list[GuardrailVerdictOut] = []
    for phase in ("input", "output"):
        for step in body.bundle.model_dump()[phase]:
            v = await _run_step(step=step, text=body.prompt)
            verdicts.append(v)

    final = resolve_final_decision([v.decision for v in verdicts])
    return TestResponse(
        prompt=body.prompt,
        verdicts=verdicts,
        final_decision=final,
    )


async def _run_step(*, step: dict, text: str) -> GuardrailVerdictOut:
    """Dispatch to the appropriate heuristic implementation for live-test.

    Network-backed providers (openai_moderation, llamaguard, custom
    classifier) are skipped and return ``allow`` so the live-test stays
    offline. The UI surfaces this via the verdict reason.
    """
    kind = step["kind"]
    on_match = step.get("on_match", "block")
    config = step.get("config") or {}

    if kind == "regex":
        return _run_regex_heuristic(config=config, text=text, on_match=on_match)

    if kind == "prompt_injection_classifier":
        return await _run_prompt_injection_heuristic(text=text, on_match=on_match)

    if kind == "secret_scanner":
        return _run_secret_scanner_heuristic(text=text, on_match=on_match)

    # Network-backed kinds: don't run them in live-test.
    return GuardrailVerdictOut(
        guardrail=kind,
        decision="allow",
        reason="live-test does not invoke network-backed providers",
    )


def _run_regex_heuristic(
    *, config: dict, text: str, on_match: str
) -> GuardrailVerdictOut:
    import re

    pattern = config.get("pattern")
    flags = re.IGNORECASE if config.get("ignore_case") else 0
    if not isinstance(pattern, str) or not pattern:
        return GuardrailVerdictOut(
            guardrail="regex", decision="allow", reason="no pattern configured"
        )
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return GuardrailVerdictOut(
            guardrail="regex",
            decision="allow",
            reason=f"invalid pattern: {exc}",
        )
    matches: list[GuardrailMatchOut] = []
    for m in rx.finditer(text):
        matches.append(
            GuardrailMatchOut(
                kind="regex.match",
                span=(m.start(), m.end()),
                evidence=m.group(0)[:80],
            )
        )
    if not matches:
        return GuardrailVerdictOut(guardrail="regex", decision="allow")
    decision = on_match if on_match in ACTION_PRIORITY else "block"
    return GuardrailVerdictOut(
        guardrail="regex",
        decision=decision,
        matches=matches,
        reason=f"{len(matches)} regex hit(s)",
    )


async def _run_prompt_injection_heuristic(
    *, text: str, on_match: str
) -> GuardrailVerdictOut:
    """Reuse the gateway-shape heuristic, repackaged into the rich shape."""
    from ai_portal.guardrails.gateway_shape.providers.prompt_injection import (
        PromptInjectionGuardrail,
    )

    gr = PromptInjectionGuardrail()
    v = await gr.scan(text)
    matches = [
        GuardrailMatchOut(
            kind=h.category,
            span=(
                (h.start, h.end) if (h.start is not None and h.end is not None) else None
            ),
            evidence=h.matched,
        )
        for h in v.hits
    ]
    if not v.flagged:
        return GuardrailVerdictOut(
            guardrail="prompt_injection_classifier",
            decision="allow",
            matches=matches,
        )
    decision = on_match if on_match in ACTION_PRIORITY else "block"
    return GuardrailVerdictOut(
        guardrail="prompt_injection_classifier",
        decision=decision,
        matches=matches,
        reason=f"{len(v.hits)} heuristic hit(s)",
    )


def _run_secret_scanner_heuristic(
    *, text: str, on_match: str
) -> GuardrailVerdictOut:
    """Very small built-in regex set for common secret shapes.

    Real provider lives at
    :class:`ai_portal.guardrails.providers.secret_scanner.SecretScannerGuardrail`
    — but it uses the rich ``check_input``/``check_output`` shape with a
    ``GuardrailContext``. Live-test wants a single text scan, so we do a
    compact in-line scan here. Matches Kept conservative to avoid false
    positives in the editor preview.
    """
    import re

    patterns = (
        ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
        ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
        ("private_key", re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----")),
    )
    matches: list[GuardrailMatchOut] = []
    for kind, rx in patterns:
        for m in rx.finditer(text):
            matches.append(
                GuardrailMatchOut(
                    kind=kind,
                    span=(m.start(), m.end()),
                    evidence=m.group(0)[:8] + "…",
                )
            )
    if not matches:
        return GuardrailVerdictOut(guardrail="secret_scanner", decision="allow")
    decision = on_match if on_match in ACTION_PRIORITY else "block"
    return GuardrailVerdictOut(
        guardrail="secret_scanner",
        decision=decision,
        matches=matches,
        reason=f"{len(matches)} secret(s) detected",
    )


__all__ = ["router"]
