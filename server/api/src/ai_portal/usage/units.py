"""Usage units catalog — every metered fact uses one of these unit keys.

A unit pins both the dimension (tokens, embeddings, queries, minutes, GB) and
the granularity (input vs output, cache read vs write). Per-event cost is
computed at write time from a frozen pricing snapshot so historical totals
never drift when pricing changes.
"""
from __future__ import annotations

from enum import Enum


class UsageUnit(str, Enum):
    tokens_in = "tokens_in"
    tokens_out = "tokens_out"
    tokens_cache_read = "tokens_cache_read"
    tokens_cache_write = "tokens_cache_write"
    embeddings = "embeddings"
    documents_ingested = "documents_ingested"
    queries = "queries"
    worker_minutes = "worker_minutes"
    storage_gb = "storage_gb"


ALL_UNITS: tuple[str, ...] = tuple(u.value for u in UsageUnit)


# Per-unit pricing fallback (USD per unit). Used when the caller does not pass
# a model-specific pricing snapshot. Token rates here are the "no-model"
# fallback — for LLM calls always pass model + use compute_event_cost().
_DEFAULT_UNIT_PRICES_USD = {
    UsageUnit.embeddings.value: 0.0,           # cheap, computed elsewhere
    UsageUnit.documents_ingested.value: 0.0,   # free
    UsageUnit.queries.value: 0.0,              # free
    UsageUnit.worker_minutes.value: 0.05,      # 3 USD/hour default
    UsageUnit.storage_gb.value: 0.023,         # S3-ish
}


def default_unit_price_usd(unit: str) -> float:
    return _DEFAULT_UNIT_PRICES_USD.get(unit, 0.0)
