"""Pure-logic tests for guardrail policy validators.

No DB / network. Mirrors the frontend's validation expectations so the
live-test endpoint rejects malformed bundles the same way the UI does.
"""

from __future__ import annotations

import pytest

from ai_portal.guardrails.policy_validators import (
    is_valid,
    normalize_bundle,
    resolve_final_decision,
    validate_bundle,
    validate_phase,
    validate_step,
)


# ── validate_step ────────────────────────────────────────────────────────


def test_step_valid():
    errs = validate_step(
        {"kind": "regex", "config": {"pattern": "foo"}, "on_match": "block"},
        path="input[0]",
    )
    assert errs == []


def test_step_missing_kind():
    errs = validate_step(
        {"config": {}, "on_match": "block"}, path="input[0]"
    )
    assert any(e.path == "input[0].kind" for e in errs)


def test_step_unknown_kind():
    errs = validate_step(
        {"kind": "telepathy", "config": {}, "on_match": "block"}, path="x"
    )
    assert any("unknown kind" in e.message for e in errs)


def test_step_invalid_on_match():
    errs = validate_step(
        {"kind": "regex", "config": {}, "on_match": "ignite"}, path="x"
    )
    assert any(e.path == "x.on_match" for e in errs)


def test_step_invalid_config_type():
    errs = validate_step(
        {"kind": "regex", "config": "not-an-object", "on_match": "block"},
        path="x",
    )
    assert any(e.path == "x.config" for e in errs)


def test_step_not_a_dict():
    errs = validate_step("hello", path="input[0]")
    assert errs and errs[0].path == "input[0]"


# ── validate_phase ───────────────────────────────────────────────────────


def test_phase_none_is_ok():
    assert validate_phase(None, phase="input") == []


def test_phase_must_be_list():
    errs = validate_phase({"not": "a list"}, phase="input")
    assert errs and errs[0].path == "input"


def test_phase_collects_step_errors():
    errs = validate_phase(
        [
            {"kind": "regex", "config": {}, "on_match": "block"},
            {"kind": "nope", "config": {}, "on_match": "block"},
        ],
        phase="output",
    )
    paths = [e.path for e in errs]
    assert "output[1].kind" in paths
    assert "output[0].kind" not in paths


# ── validate_bundle ──────────────────────────────────────────────────────


def test_bundle_empty_is_valid():
    assert is_valid({"input": [], "output": []})
    assert is_valid({})


def test_bundle_unknown_phase_rejected():
    errs = validate_bundle({"input": [], "middle": []})
    assert any(e.path == "middle" for e in errs)


def test_bundle_not_an_object_rejected():
    errs = validate_bundle([])
    assert errs and "bundle must be an object" in errs[0].message


def test_bundle_real_valid_example():
    bundle = {
        "input": [
            {"kind": "regex", "config": {"pattern": "ssn"}, "on_match": "redact"},
            {"kind": "prompt_injection_classifier", "config": {}, "on_match": "block"},
        ],
        "output": [
            {"kind": "secret_scanner", "config": {}, "on_match": "redact"},
        ],
    }
    assert is_valid(bundle)


# ── resolve_final_decision ───────────────────────────────────────────────


def test_resolve_empty_is_allow():
    assert resolve_final_decision([]) == "allow"


def test_resolve_strongest_wins():
    assert resolve_final_decision(["allow", "flag", "redact"]) == "redact"
    assert resolve_final_decision(["redact", "block"]) == "block"
    assert resolve_final_decision(["flag", "flag", "allow"]) == "flag"


def test_resolve_unknown_treated_as_allow():
    assert resolve_final_decision(["mystery", "flag"]) == "flag"


# ── normalize_bundle ─────────────────────────────────────────────────────


def test_normalize_fills_missing_phases():
    assert normalize_bundle({}) == {"input": [], "output": []}
    assert normalize_bundle({"input": [{"kind": "regex"}]}) == {
        "input": [{"kind": "regex"}],
        "output": [],
    }


def test_normalize_copies_lists():
    src = {"input": [{"kind": "regex"}]}
    out = normalize_bundle(src)
    out["input"].append({"kind": "presidio"})
    # original untouched
    assert len(src["input"]) == 1
