"""Catalog sync — refresh the ``gateway_models`` table from provider APIs.

Runs daily. For each enabled provider, calls ``list_models()`` and upserts
each returned :class:`ModelInfo` into ``gateway_models``. Idempotent.

Each provider implements a thin coroutine returning ``list[ModelInfo]`` —
the gateway-canonical shape (provider, model_id, display_name, capabilities,
prices). New providers added by registering in
``catalog.sync.DEFAULT_PROVIDERS``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ai_portal.catalog.model import GatewayModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelInfo:
    """One row's worth of model metadata as reported by a provider."""

    provider: str
    model_id: str
    display_name: str
    capabilities: list[str] = field(default_factory=list)
    price_input_per_1k_cents: int = 0
    price_output_per_1k_cents: int = 0
    price_cache_read_per_1k_cents: int = 0
    deprecated_at: datetime | None = None


class _ListsModels(Protocol):
    name: str

    async def list_models(self) -> list[ModelInfo]: ...


async def sync_models(db: Session, providers: list[_ListsModels]) -> int:
    """Upsert every provider's models into ``gateway_models``.

    Returns the number of rows touched (inserted + updated).
    Idempotent — replays produce the same final state.
    """
    touched = 0
    for provider in providers:
        try:
            models = await provider.list_models()
        except Exception as exc:  # never let one provider sink the sync
            logger.warning(
                "catalog.sync: provider=%s list_models failed: %s",
                getattr(provider, "name", "?"),
                exc,
            )
            continue

        for m in models:
            stmt = (
                pg_insert(GatewayModel)
                .values(
                    provider=m.provider,
                    model_id=m.model_id,
                    display_name=m.display_name,
                    capabilities_json=list(m.capabilities),
                    price_input_per_1k_cents=m.price_input_per_1k_cents,
                    price_output_per_1k_cents=m.price_output_per_1k_cents,
                    price_cache_read_per_1k_cents=m.price_cache_read_per_1k_cents,
                    deprecated_at=m.deprecated_at,
                )
                .on_conflict_do_update(
                    constraint="uq_gateway_models_provider_model",
                    set_={
                        "display_name": m.display_name,
                        "capabilities_json": list(m.capabilities),
                        "price_input_per_1k_cents": m.price_input_per_1k_cents,
                        "price_output_per_1k_cents": m.price_output_per_1k_cents,
                        "price_cache_read_per_1k_cents": m.price_cache_read_per_1k_cents,
                        "deprecated_at": m.deprecated_at,
                    },
                )
            )
            db.execute(stmt)
            touched += 1

    return touched


def list_all_models(db: Session, *, provider: str | None = None) -> list[GatewayModel]:
    """Return every gateway_models row, optionally filtered by provider."""
    stmt = select(GatewayModel).order_by(
        GatewayModel.provider, GatewayModel.model_id
    )
    if provider:
        stmt = stmt.where(GatewayModel.provider == provider)
    return list(db.scalars(stmt).all())
