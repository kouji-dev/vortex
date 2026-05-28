"""Catalog sync — refresh the ``gateway_models`` table from provider APIs.

Runs daily. For each enabled provider, calls ``list_models()`` and upserts
each returned :class:`ModelInfo` into ``gateway_models``. Idempotent.

Each provider implements a thin coroutine returning ``list[ModelInfo]`` —
the gateway-canonical shape (provider, model_id, display_name, capabilities,
prices). New providers added by registering in
``catalog.sync.DEFAULT_PROVIDERS``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ai_portal.catalog.model import GatewayModel

logger = logging.getLogger(__name__)

# Daily refresh — 24h.
DEFAULT_SYNC_INTERVAL_SECONDS: float = 24 * 60 * 60
# Health probe — every 5 minutes.
DEFAULT_HEALTH_INTERVAL_SECONDS: float = 5 * 60


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


# ── default-provider registry ──────────────────────────────────────────────

ProviderFactory = Callable[[], _ListsModels]
DEFAULT_PROVIDERS: list[ProviderFactory] = []


def register_default_provider(factory: ProviderFactory) -> None:
    """Register a provider factory used by ``sync_all_providers``."""
    DEFAULT_PROVIDERS.append(factory)


def _resolve_providers(
    providers: list[_ListsModels] | None,
) -> list[_ListsModels]:
    if providers is not None:
        return providers
    return [f() for f in DEFAULT_PROVIDERS]


# ── high-level orchestrators ───────────────────────────────────────────────

async def sync_all_providers(
    providers: list[_ListsModels] | None = None,
    *,
    db_factory: Callable[[], Session] | None = None,
) -> int:
    """Run one full catalog sync. Returns rows touched.

    ``providers`` defaults to ``DEFAULT_PROVIDERS``. ``db_factory`` defaults
    to ``SessionLocal``.
    """
    resolved = _resolve_providers(providers)
    if not resolved:
        logger.info("catalog.sync: no providers configured")
        return 0

    if db_factory is None:
        from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415

        db_factory = SessionLocal

    db = db_factory()
    try:
        from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415

        with bypass_rls(db):
            touched = await sync_models(db, resolved)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("catalog.sync_all_providers failed: %s", exc)
        db.rollback()
        return 0
    finally:
        db.close()

    logger.info("catalog.sync_all_providers: touched=%s", touched)
    return touched


async def probe_health(
    providers: list[_ListsModels] | None = None,
) -> dict[str, bool]:
    """Probe ``health()`` on every provider. Returns mapping name→healthy.

    Failures are caught and logged; never raises.
    """
    resolved = _resolve_providers(providers)
    out: dict[str, bool] = {}
    for p in resolved:
        name = getattr(p, "name", type(p).__name__)
        try:
            health_fn = getattr(p, "health", None)
            if health_fn is None:
                out[name] = True
                continue
            result = await health_fn()
            out[name] = bool(getattr(result, "healthy", True))
        except Exception as exc:  # noqa: BLE001
            logger.warning("catalog.health: provider=%s failed: %s", name, exc)
            out[name] = False
    return out


# ── background scheduler ───────────────────────────────────────────────────


async def _run_loop(
    fn: Callable[[], Awaitable[object]],
    *,
    interval: float,
    name: str,
    initial_delay: float = 0.0,
) -> None:
    """Run ``fn`` forever every ``interval`` seconds. Logs but swallows errors."""
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("catalog.scheduler[%s] iteration failed: %s", name, exc)
        await asyncio.sleep(interval)


def start_background_scheduler(
    *,
    providers: list[_ListsModels] | None = None,
    sync_interval: float = DEFAULT_SYNC_INTERVAL_SECONDS,
    health_interval: float = DEFAULT_HEALTH_INTERVAL_SECONDS,
    run_initial_sync: bool = True,
) -> list[asyncio.Task[None]]:
    """Start daily-sync + health-probe background tasks. Returns task handles.

    Caller owns the tasks — must cancel + await on shutdown.
    """
    async def _sync_once() -> None:
        await sync_all_providers(providers)

    async def _health_once() -> None:
        await probe_health(providers)

    tasks = [
        asyncio.create_task(
            _run_loop(
                _sync_once,
                interval=sync_interval,
                name="sync",
                initial_delay=0.0 if run_initial_sync else sync_interval,
            ),
            name="catalog-sync-loop",
        ),
        asyncio.create_task(
            _run_loop(
                _health_once,
                interval=health_interval,
                name="health",
                initial_delay=health_interval,
            ),
            name="catalog-health-loop",
        ),
    ]
    return tasks


async def stop_background_scheduler(tasks: list[asyncio.Task[None]]) -> None:
    """Cancel + await scheduler tasks. Swallows CancelledError."""
    for t in tasks:
        t.cancel()
    for t in tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
