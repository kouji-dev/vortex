"""K2: Chat module routes LLM calls through the gateway facade.

The chat ``iteration_loop`` no longer talks to providers directly. It calls
:func:`ai_portal.gateway.chat_bridge.stream_chat_legacy` which wraps the
legacy ChatProvider stream and writes a ``request_traces`` row at end of
stream so chat calls show up in gateway observability alongside compat-
endpoint traffic.

Behavior preserved:

- Same events surfaced to the caller (llm_call + assistant_text items).
- Provider invoked exactly once per LLM iteration.
- The existing audit + usage emission from ``iteration_loop`` is untouched.

Added (via the gateway bridge):

- A :class:`ai_portal.gateway.traces.writer.TraceRecord` is emitted with
  ``route='chat.stream'``, token counts populated, and ``actor.user_id``
  preserved.

These tests are DB-free: they use a stub ``ItemWriter`` so the test
exercises the chat→gateway contract without touching Postgres.
"""

from __future__ import annotations

import uuid

import pytest

from ai_portal.catalog.providers.events import ProviderStreamEvent
from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.model import ThreadItem
from ai_portal.chat.streaming import iteration_loop
from ai_portal.gateway import set_default_facade
from ai_portal.gateway.facade import FacadeConfig, GatewayFacade

pytestmark = pytest.mark.asyncio


_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000cf2")
_USER_ID = 99902


# ── fakes ────────────────────────────────────────────────────────────────


class FakeProvider:
    """Fake legacy ChatProvider — yields scripted ProviderStreamEvent values."""

    name = "fake-provider"

    def __init__(self, scripts: list[list[dict]]) -> None:
        self._scripts = list(scripts)
        self._i = 0
        self.calls = 0

    async def stream(self, *, messages=None, model=None, settings=None, tools=None, **kwargs):
        self.calls += 1
        script = self._scripts[self._i]
        self._i += 1
        for e in script:
            yield ProviderStreamEvent.model_validate(e)


class StubItemWriter:
    """In-memory ItemWriter — same surface as the real one, no DB."""

    def __init__(self) -> None:
        self.session = object()  # non-Async name so audit path runs
        self.thread_id = 1
        self.org_id = _ORG_ID
        self._next_id = 1
        self.items: list[ThreadItem] = []

    def _new(self, **kw) -> ThreadItem:
        item = ThreadItem(
            id=self._next_id,
            thread_id=self.thread_id,
            org_id=self.org_id,
            status=ItemStatus.streaming,
            cost_estimated=True,
            **kw,
        )
        self._next_id += 1
        self.items.append(item)
        return item

    def start_llm_call(self, *, turn_id, model, iteration_index):
        return self._new(
            turn_id=turn_id, kind=ItemKind.llm_call, role=ItemRole.assistant,
            model=model,
            data={"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0,
                  "cache_creation_input_tokens": 0, "reasoning_tokens": 0,
                  "iteration_index": iteration_index},
        )

    def start_text(self, *, turn_id):
        return self._new(
            turn_id=turn_id, kind=ItemKind.assistant_text, role=ItemRole.assistant,
            data={"text": ""},
        )

    def start_thinking(self, *, turn_id):
        return self._new(
            turn_id=turn_id, kind=ItemKind.thinking, role=ItemRole.assistant,
            data={"text": ""},
        )

    def append_text_delta(self, item_id, text):
        for it in self.items:
            if it.id == item_id:
                it.data["text"] += text

    def finalize_text(self, item_id):
        for it in self.items:
            if it.id == item_id:
                it.status = ItemStatus.done
                return it
        raise KeyError(item_id)

    def finalize_thinking(self, item_id):
        return self.finalize_text(item_id)

    def finish_llm_call(self, *, item_id, input_tokens, output_tokens,
                        cached_input_tokens, cache_creation_input_tokens,
                        reasoning_tokens, cost_usd, cost_estimated):
        for it in self.items:
            if it.id == item_id:
                it.status = ItemStatus.done
                it.cost_usd = cost_usd
                it.cost_estimated = cost_estimated
                it.data.update({
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "cache_creation_input_tokens": cache_creation_input_tokens,
                    "reasoning_tokens": reasoning_tokens,
                })
                return it
        raise KeyError(item_id)

    def fail_llm_call(self, *, item_id, error):
        for it in self.items:
            if it.id == item_id:
                it.status = ItemStatus.error
                it.data["error"] = error
                return it
        raise KeyError(item_id)

    def cancel_turn_items(self, *, turn_id):
        n = 0
        for it in self.items:
            if it.turn_id == turn_id and it.status == ItemStatus.streaming:
                it.status = ItemStatus.cancelled
                n += 1
        return n

    def insert_citation(self, **kw):
        return self._new(kind=ItemKind.citation, role=ItemRole.system, data=kw)


# ── facade fixture ───────────────────────────────────────────────────────


@pytest.fixture
def trace_sink():
    """Install a stub facade that records trace rows; yield the sink list."""
    captured: list = []
    audit_log: list = []
    usage_log: list = []

    def _emit_trace(record):
        captured.append(record)

    def _emit_audit(**kw):
        audit_log.append(kw)

    def _emit_usage(**kw):
        usage_log.append(kw)

    cfg = FacadeConfig(
        resolve_provider=lambda req, actor: None,  # type: ignore[arg-type,return-value]
        emit_trace=_emit_trace,
        emit_audit=_emit_audit,
        emit_usage=_emit_usage,
    )
    facade = GatewayFacade(cfg)
    token = set_default_facade(facade)
    try:
        yield captured
    finally:
        set_default_facade(token)


# ── tests ────────────────────────────────────────────────────────────────


async def test_iteration_loop_writes_trace_via_gateway(trace_sink):
    """A successful turn must write one trace row via the gateway facade."""
    turn_id = uuid.uuid4()
    script = [
        {"type": "text_delta", "text": "ok"},
        {"type": "usage", "input_tokens": 11, "output_tokens": 5,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]
    provider = FakeProvider([script])
    writer = StubItemWriter()

    async for _ev in iteration_loop.run(
        provider=provider,
        writer=writer,
        turn_id=turn_id,
        provider_messages=[{"role": "system", "content": "Be helpful."}],
        model="gpt-4",
        allowed_tools=[],
        max_iterations=3,
        org_id=_ORG_ID,
        user_id=_USER_ID,
    ):
        pass

    # Provider invoked once.
    assert provider.calls == 1
    # Gateway facade wrote one trace row.
    assert len(trace_sink) == 1
    rec = trace_sink[0]
    assert rec.route == "chat.stream"
    assert rec.tokens_in == 11
    assert rec.tokens_out == 5
    assert rec.model_used == "gpt-4"
    assert rec.status == "ok"
    assert rec.org_id == _ORG_ID
    assert rec.actor_json["user_id"] == _USER_ID


async def test_iteration_loop_still_yields_events(trace_sink):
    """Refactor must not change the events surfaced to the caller."""
    turn_id = uuid.uuid4()
    script = [
        {"type": "text_delta", "text": "Hi "},
        {"type": "text_delta", "text": "there"},
        {"type": "usage", "input_tokens": 4, "output_tokens": 2,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]
    provider = FakeProvider([script])
    writer = StubItemWriter()

    events = []
    async for ev in iteration_loop.run(
        provider=provider,
        writer=writer,
        turn_id=turn_id,
        provider_messages=[],
        model="gpt-4",
        allowed_tools=[],
        max_iterations=3,
        org_id=_ORG_ID,
        user_id=_USER_ID,
    ):
        events.append(ev)

    item_events = [e.root for e in events if e.root.event_type == "item"]
    kinds = [ev.item.root.kind for ev in item_events]
    assert "llm_call" in kinds
    assert "assistant_text" in kinds


async def test_trace_records_error_status_on_provider_error(trace_sink):
    """Provider error → trace row with status='error'.

    iteration_loop wraps the bridge in ``contextlib.aclosing`` so the
    bridge's ``finally`` block runs deterministically when the loop body
    raises.
    """
    turn_id = uuid.uuid4()

    class _BoomProvider:
        name = "boom"

        async def stream(self, **_kw):
            yield ProviderStreamEvent.model_validate(
                {"type": "provider_error", "code": "boom", "message": "kaboom"}
            )

    writer = StubItemWriter()
    with pytest.raises(RuntimeError):
        async for _ in iteration_loop.run(
            provider=_BoomProvider(),
            writer=writer,
            turn_id=turn_id,
            provider_messages=[],
            model="gpt-4",
            allowed_tools=[],
            max_iterations=1,
            org_id=_ORG_ID,
            user_id=_USER_ID,
        ):
            pass

    assert len(trace_sink) == 1
    assert trace_sink[0].status == "error"


async def test_trace_skipped_when_no_facade_installed():
    """Without a default facade, chat must still work — trace just no-ops."""
    prev = set_default_facade(None)
    try:
        turn_id = uuid.uuid4()
        script = [
            {"type": "text_delta", "text": "ok"},
            {"type": "usage", "input_tokens": 2, "output_tokens": 1,
             "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
            {"type": "iteration_complete", "stop_reason": "end_turn"},
        ]
        provider = FakeProvider([script])
        writer = StubItemWriter()
        async for _ev in iteration_loop.run(
            provider=provider,
            writer=writer,
            turn_id=turn_id,
            provider_messages=[],
            model="gpt-4",
            allowed_tools=[],
            max_iterations=1,
            org_id=_ORG_ID,
            user_id=_USER_ID,
        ):
            pass
        # No exceptions — chat works without a facade.
        assert provider.calls == 1
    finally:
        set_default_facade(prev)
