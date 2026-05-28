"""catalog.sync — scheduler / sync_all_providers / probe_health.

Pure-logic tests (no DB). Mocks providers + db_factory.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


class _FakeProvider:
    def __init__(self, name: str, models: list[dict], *, healthy: bool = True, raise_health: bool = False) -> None:
        self.name = name
        self._models = models
        self.calls = 0
        self._healthy = healthy
        self._raise_health = raise_health

    async def list_models(self):
        from ai_portal.catalog.sync import ModelInfo

        self.calls += 1
        return [ModelInfo(**m) for m in self._models]

    async def health(self):
        if self._raise_health:
            raise RuntimeError("probe boom")

        @dataclass
        class _H:
            healthy: bool

        return _H(self._healthy)


class _StubSession:
    """Tiny session stand-in capturing sync_models calls."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.executed: list = []

    def execute(self, stmt):
        self.executed.append(stmt)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _patch_bypass_rls(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def _noop(_db):
        yield

    import ai_portal.core.db.rls as rls_mod

    monkeypatch.setattr(rls_mod, "bypass_rls", _noop)


def test_sync_all_providers_uses_default_registry(monkeypatch):
    from ai_portal.catalog import sync as sync_mod

    fake = _FakeProvider(
        "anthropic",
        [
            {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-6",
                "display_name": "Claude Sonnet 4.6",
                "capabilities": ["chat"],
                "price_input_per_1k_cents": 30,
                "price_output_per_1k_cents": 150,
                "price_cache_read_per_1k_cents": 3,
            }
        ],
    )

    monkeypatch.setattr(sync_mod, "DEFAULT_PROVIDERS", [lambda: fake])
    stub = _StubSession()
    _patch_bypass_rls(monkeypatch)

    touched = asyncio.run(
        sync_mod.sync_all_providers(db_factory=lambda: stub)
    )

    assert touched == 1
    assert fake.calls == 1
    assert stub.commits == 1
    assert stub.closed is True


def test_sync_all_providers_empty_when_no_providers(monkeypatch):
    from ai_portal.catalog import sync as sync_mod

    monkeypatch.setattr(sync_mod, "DEFAULT_PROVIDERS", [])
    stub = _StubSession()

    touched = asyncio.run(
        sync_mod.sync_all_providers(db_factory=lambda: stub)
    )

    assert touched == 0
    # Session never even opened in the no-provider path.
    assert stub.commits == 0


def test_sync_all_providers_explicit_overrides_registry(monkeypatch):
    from ai_portal.catalog import sync as sync_mod

    registry_provider = _FakeProvider("reg", [])
    explicit_provider = _FakeProvider(
        "openai",
        [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "display_name": "GPT-4o",
                "capabilities": ["chat"],
                "price_input_per_1k_cents": 250,
                "price_output_per_1k_cents": 1000,
                "price_cache_read_per_1k_cents": 125,
            }
        ],
    )

    monkeypatch.setattr(sync_mod, "DEFAULT_PROVIDERS", [lambda: registry_provider])
    stub = _StubSession()
    _patch_bypass_rls(monkeypatch)

    touched = asyncio.run(
        sync_mod.sync_all_providers(
            [explicit_provider], db_factory=lambda: stub
        )
    )

    assert touched == 1
    assert explicit_provider.calls == 1
    assert registry_provider.calls == 0


def test_sync_all_providers_rolls_back_on_db_failure(monkeypatch):
    from ai_portal.catalog import sync as sync_mod

    fake = _FakeProvider(
        "openai",
        [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "display_name": "GPT-4o",
                "capabilities": ["chat"],
                "price_input_per_1k_cents": 250,
                "price_output_per_1k_cents": 1000,
                "price_cache_read_per_1k_cents": 125,
            }
        ],
    )

    class _BoomSession(_StubSession):
        def execute(self, stmt):
            raise RuntimeError("db down")

    stub = _BoomSession()
    _patch_bypass_rls(monkeypatch)

    touched = asyncio.run(
        sync_mod.sync_all_providers([fake], db_factory=lambda: stub)
    )

    assert touched == 0
    assert stub.rollbacks == 1
    assert stub.closed is True


def test_probe_health_returns_mapping(monkeypatch):
    from ai_portal.catalog import sync as sync_mod

    good = _FakeProvider("anthropic", [], healthy=True)
    bad = _FakeProvider("openai", [], healthy=False)
    boom = _FakeProvider("gemini", [], raise_health=True)

    monkeypatch.setattr(
        sync_mod, "DEFAULT_PROVIDERS", [lambda: good, lambda: bad, lambda: boom]
    )

    out = asyncio.run(sync_mod.probe_health())

    assert out == {"anthropic": True, "openai": False, "gemini": False}


def test_start_and_stop_background_scheduler(monkeypatch):
    """Scheduler runs immediate sync once then health probe at interval."""
    from ai_portal.catalog import sync as sync_mod

    sync_calls = 0
    health_calls = 0

    async def _fake_sync(providers=None, *, db_factory=None):
        nonlocal sync_calls
        sync_calls += 1
        return 0

    async def _fake_health(providers=None):
        nonlocal health_calls
        health_calls += 1
        return {}

    monkeypatch.setattr(sync_mod, "sync_all_providers", _fake_sync)
    monkeypatch.setattr(sync_mod, "probe_health", _fake_health)

    async def _run() -> tuple[int, int]:
        tasks = sync_mod.start_background_scheduler(
            sync_interval=0.05,
            health_interval=0.05,
        )
        # Let initial sync fire + at least one health tick.
        await asyncio.sleep(0.15)
        await sync_mod.stop_background_scheduler(tasks)
        return sync_calls, health_calls

    s, h = asyncio.run(_run())
    assert s >= 1
    assert h >= 1
