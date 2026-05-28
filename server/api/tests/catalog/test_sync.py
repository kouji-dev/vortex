"""A3: catalog.sync — daily provider model upsert is idempotent."""

from __future__ import annotations

import ai_portal.catalog.model  # noqa: F401  (ensure metadata loaded)
from tests.conftest import requires_postgres


class _FakeProvider:
    def __init__(self, name: str, models: list[dict]) -> None:
        self.name = name
        self._models = models
        self.calls = 0

    async def list_models(self):
        from ai_portal.catalog.sync import ModelInfo  # local import

        self.calls += 1
        return [ModelInfo(**m) for m in self._models]


@requires_postgres
def test_sync_inserts_then_is_idempotent():
    import asyncio

    from sqlalchemy import delete, select

    from ai_portal.catalog.model import GatewayModel
    from ai_portal.catalog.sync import sync_models
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    fake = _FakeProvider(
        "anthropic",
        [
            {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-6",
                "display_name": "Claude Sonnet 4.6",
                "capabilities": ["chat", "vision", "tools", "thinking", "cache"],
                "price_input_per_1k_cents": 30,
                "price_output_per_1k_cents": 150,
                "price_cache_read_per_1k_cents": 3,
            },
            {
                "provider": "anthropic",
                "model_id": "claude-haiku-4-5",
                "display_name": "Claude Haiku 4.5",
                "capabilities": ["chat", "tools"],
                "price_input_per_1k_cents": 8,
                "price_output_per_1k_cents": 40,
                "price_cache_read_per_1k_cents": 1,
            },
        ],
    )

    db = SessionLocal()
    try:
        with bypass_rls(db):
            db.execute(
                delete(GatewayModel).where(GatewayModel.provider == "anthropic")
            )
            db.commit()

            asyncio.run(sync_models(db, [fake]))
            db.commit()
            rows = db.scalars(
                select(GatewayModel).where(GatewayModel.provider == "anthropic")
            ).all()
            assert len(rows) == 2
            by_id = {r.model_id: r for r in rows}
            assert by_id["claude-sonnet-4-6"].display_name == "Claude Sonnet 4.6"
            assert "vision" in by_id["claude-sonnet-4-6"].capabilities_json
            assert by_id["claude-sonnet-4-6"].price_input_per_1k_cents == 30
            assert by_id["claude-haiku-4-5"].price_output_per_1k_cents == 40

            # Second call — same data, upsert keeps row count stable.
            asyncio.run(sync_models(db, [fake]))
            db.commit()
            rows2 = db.scalars(
                select(GatewayModel).where(GatewayModel.provider == "anthropic")
            ).all()
            assert len(rows2) == 2
            # No duplicate ids
            assert {r.id for r in rows2} == {r.id for r in rows}
    finally:
        with bypass_rls(db):
            db.execute(
                delete(GatewayModel).where(GatewayModel.provider == "anthropic")
            )
            db.commit()
        db.close()


@requires_postgres
def test_sync_updates_pricing_on_change():
    import asyncio

    from sqlalchemy import delete, select

    from ai_portal.catalog.model import GatewayModel
    from ai_portal.catalog.sync import sync_models
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    base = {
        "provider": "openai",
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
        "capabilities": ["chat", "vision"],
        "price_input_per_1k_cents": 250,
        "price_output_per_1k_cents": 1000,
        "price_cache_read_per_1k_cents": 125,
    }
    p1 = _FakeProvider("openai", [base])
    bumped = {**base, "price_input_per_1k_cents": 300, "display_name": "GPT-4o (new)"}
    p2 = _FakeProvider("openai", [bumped])

    db = SessionLocal()
    try:
        with bypass_rls(db):
            db.execute(
                delete(GatewayModel).where(GatewayModel.provider == "openai")
            )
            db.commit()

            asyncio.run(sync_models(db, [p1]))
            db.commit()
            asyncio.run(sync_models(db, [p2]))
            db.commit()
            row = db.scalars(
                select(GatewayModel)
                .where(GatewayModel.provider == "openai")
                .where(GatewayModel.model_id == "gpt-4o")
            ).one()
            assert row.price_input_per_1k_cents == 300
            assert row.display_name == "GPT-4o (new)"
    finally:
        with bypass_rls(db):
            db.execute(
                delete(GatewayModel).where(GatewayModel.provider == "openai")
            )
            db.commit()
        db.close()
