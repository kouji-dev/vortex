"""emit_usage — append a UsageEvent with frozen pricing snapshot.

This is the shared substrate. Every billable action across the suite calls
``emit_usage`` so rollups/quotas/budgets see one consistent stream.

Cost rules:
- For LLM token units, if ``model`` is known we use ``chat.llm_pricing`` and
  freeze the per-million-rate at write time into ``pricing_snapshot``.
- For non-token units, ``default_unit_price_usd`` provides a fallback rate.
- Caller may override with ``unit_price_usd`` (e.g., custom contract rate);
  it is recorded in ``pricing_snapshot`` so historical totals don't drift.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ai_portal.chat.llm_pricing import get_llm_rates
from ai_portal.usage.events_model import UsageEvent
from ai_portal.usage.units import UsageUnit, default_unit_price_usd


_MILLION = Decimal("1000000")
_ZERO = Decimal("0")

_TOKEN_UNITS = {
    UsageUnit.tokens_in.value,
    UsageUnit.tokens_out.value,
    UsageUnit.tokens_cache_read.value,
    UsageUnit.tokens_cache_write.value,
}


def _llm_rate_per_million(unit: str, model: str) -> Decimal | None:
    rates = get_llm_rates(model)
    if rates is None:
        return None
    if unit == UsageUnit.tokens_in.value:
        return rates.input_per_million
    if unit == UsageUnit.tokens_out.value:
        return rates.output_per_million
    if unit == UsageUnit.tokens_cache_read.value:
        return rates.cached_input_per_million or rates.input_per_million
    if unit == UsageUnit.tokens_cache_write.value:
        return rates.cache_creation_per_million or rates.input_per_million
    return None


def compute_event_cost(
    *,
    unit: str,
    qty: Decimal,
    model: str | None,
    unit_price_usd: Decimal | None,
) -> tuple[Decimal, dict[str, Any]]:
    """Return (cost_usd, pricing_snapshot)."""
    qty = Decimal(qty)
    # Caller-provided override always wins.
    if unit_price_usd is not None:
        price = Decimal(unit_price_usd)
        return (
            (qty * price).quantize(Decimal("0.000001")),
            {"source": "override", "unit_price_usd": str(price)},
        )

    if unit in _TOKEN_UNITS and model:
        rate = _llm_rate_per_million(unit, model)
        if rate is not None:
            cost = (qty * rate / _MILLION).quantize(Decimal("0.000001"))
            return cost, {
                "source": "llm_pricing",
                "model": model,
                "unit": unit,
                "per_million_usd": str(rate),
            }

    fallback = Decimal(str(default_unit_price_usd(unit)))
    cost = (qty * fallback).quantize(Decimal("0.000001"))
    return cost, {"source": "default", "unit": unit, "unit_price_usd": str(fallback)}


def emit_usage(
    db: Session,
    *,
    org_id: _uuid.UUID,
    unit: str,
    qty: int | float | Decimal,
    actor_kind: str,
    module: str,
    actor_user_id: int | None = None,
    actor_api_key_id: int | None = None,
    actor_team_id: int | None = None,
    model: str | None = None,
    resource_kind: str | None = None,
    resource_id: str | None = None,
    request_id: _uuid.UUID | None = None,
    idempotency_key: str | None = None,
    unit_price_usd: Decimal | None = None,
    ts: datetime | None = None,
    meta: dict[str, Any] | None = None,
) -> UsageEvent:
    """Append one UsageEvent and flush; returns the persisted row.

    Cost is computed at write time and frozen via ``pricing_snapshot`` so
    later rate changes never alter historical totals.
    """
    if unit not in {u.value for u in UsageUnit}:
        raise ValueError(f"unknown usage unit: {unit}")
    if actor_kind not in {"user", "api_key", "service", "system"}:
        raise ValueError(f"unknown actor_kind: {actor_kind}")

    qty_dec = Decimal(qty) if not isinstance(qty, Decimal) else qty
    cost, snapshot = compute_event_cost(
        unit=unit, qty=qty_dec, model=model, unit_price_usd=unit_price_usd
    )

    row = UsageEvent(
        org_id=org_id,
        ts=ts or datetime.now(timezone.utc),
        unit=unit,
        qty=qty_dec,
        cost_usd=cost,
        pricing_snapshot=snapshot,
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
        actor_api_key_id=actor_api_key_id,
        actor_team_id=actor_team_id,
        module=module,
        model=model,
        resource_kind=resource_kind,
        resource_id=resource_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        meta=meta,
    )
    db.add(row)
    db.flush()
    return row
