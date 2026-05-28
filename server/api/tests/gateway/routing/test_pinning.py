"""Model pinning — ``model: "smart@2026-05-01"`` freezes alias resolution
to candidates active at that date.

Pin parsing is a pure function; the date filter is applied to the
candidate list before the strategy picks. Models whose
``deprecated_at`` is on or before the pin date are excluded.

No DB needed — :class:`RoutingService.resolve` accepts the filtered
candidates; the pin parser is independent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from ai_portal.gateway.routing.protocol import ProviderModel, RoutingError
from ai_portal.gateway.routing.service import (
    RoutingService,
    filter_candidates_by_pin_date,
    parse_pinned_model,
)
from ai_portal.gateway.types import LLMRequest, Message, TextBlock


def _req(model: str) -> LLMRequest:
    return LLMRequest(
        model=model, messages=[Message(role="user", content=[TextBlock(text="hi")])]
    )


# ── parse_pinned_model ───────────────────────────────────────────────────


def test_parse_pinned_model_strips_date_suffix() -> None:
    base, pin = parse_pinned_model("smart@2026-05-01")
    assert base == "smart"
    assert pin == datetime(2026, 5, 1, tzinfo=UTC)


def test_parse_pinned_model_no_suffix_returns_none() -> None:
    base, pin = parse_pinned_model("gpt-4o")
    assert base == "gpt-4o"
    assert pin is None


def test_parse_pinned_model_rejects_invalid_date() -> None:
    # No @ → identity; bad date → ValueError so callers can 400.
    with pytest.raises(ValueError):
        parse_pinned_model("smart@not-a-date")


def test_parse_pinned_model_supports_full_iso() -> None:
    _, pin = parse_pinned_model("smart@2026-05-01T12:00:00+00:00")
    assert pin == datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)


# ── filter_candidates_by_pin_date ────────────────────────────────────────


def test_filter_excludes_models_deprecated_before_pin() -> None:
    pin = datetime(2026, 5, 1, tzinfo=UTC)
    cands = [
        ProviderModel(provider="openai", model_id="gpt-4o", capabilities=frozenset(),
                      deprecated_at=None),
        ProviderModel(
            provider="openai", model_id="gpt-3", capabilities=frozenset(),
            deprecated_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        ProviderModel(
            provider="anthropic",
            model_id="claude-3",
            capabilities=frozenset(),
            deprecated_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    ]
    out = filter_candidates_by_pin_date(cands, pin)
    # gpt-3 deprecated before pin → out; claude-3 deprecated after pin → in.
    ids = {(c.provider, c.model_id) for c in out}
    assert ("openai", "gpt-3") not in ids
    assert ("openai", "gpt-4o") in ids
    assert ("anthropic", "claude-3") in ids


def test_filter_empty_when_all_deprecated_before_pin() -> None:
    pin = datetime(2026, 5, 1, tzinfo=UTC)
    cands = [
        ProviderModel(
            provider="x", model_id="old",
            capabilities=frozenset(),
            deprecated_at=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    ]
    assert filter_candidates_by_pin_date(cands, pin) == []


def test_filter_no_pin_returns_input_unchanged() -> None:
    cands = [
        ProviderModel(provider="x", model_id="a", capabilities=frozenset()),
    ]
    out = filter_candidates_by_pin_date(cands, None)
    assert out == cands


# ── service.resolve handles pinned alias ─────────────────────────────────


def test_resolve_with_pinned_concrete_model_strips_suffix() -> None:
    """Concrete model pinned to a date — same candidate when active."""
    svc = RoutingService(db=None)  # type: ignore[arg-type]
    cands = [
        ProviderModel(
            provider="anthropic",
            model_id="claude-sonnet-4-6",
            capabilities=frozenset(),
            deprecated_at=None,
        ),
    ]
    res = svc.resolve(
        req=_req(model="claude-sonnet-4-6@2026-05-01"),
        org_id=uuid.uuid4(),
        candidates=cands,
    )
    assert res.candidate.model_id == "claude-sonnet-4-6"
    assert res.pin_date == datetime(2026, 5, 1, tzinfo=UTC)


def test_resolve_pinned_concrete_model_deprecated_raises() -> None:
    """Concrete model deprecated before pin → RoutingError."""
    svc = RoutingService(db=None)  # type: ignore[arg-type]
    cands = [
        ProviderModel(
            provider="openai",
            model_id="gpt-3",
            capabilities=frozenset(),
            deprecated_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
    ]
    with pytest.raises(RoutingError):
        svc.resolve(
            req=_req(model="gpt-3@2026-05-01"),
            org_id=uuid.uuid4(),
            candidates=cands,
        )
