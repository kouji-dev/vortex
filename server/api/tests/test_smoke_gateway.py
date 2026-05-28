"""Phase 3 — Gateway smoke test.

Boots the full FastAPI app against a scratch Postgres DB, wires the
:class:`GatewayFacade` with a :class:`FakeProvider`, then drives the
OpenAI-compatible ``POST /v1/chat/completions`` golden path and asserts:

- response shape matches OpenAI ``chat.completion``
- a ``request_traces`` row was written by the facade pipeline
- a ``usage_events`` row exists with ``unit='tokens_in'``
- an ``audit_events`` row exists with ``event_type LIKE 'gateway.%'``

The DB is created/migrated by the runner before pytest collection. The test
itself stays at the HTTP boundary — it never reaches into provider internals.
"""
from __future__ import annotations

import os
import time

import pytest
import requests
import sqlalchemy as sa

GATEWAY_BASE = os.environ.get("SMOKE_GATEWAY_URL", "http://127.0.0.1:8004")
GATEWAY_DB_URL = os.environ.get(
    "SMOKE_GATEWAY_DB_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_smoke_gw",
)
DEV_BEARER = os.environ.get("SMOKE_GATEWAY_BEARER", "devtoken")


def _server_alive() -> bool:
    try:
        r = requests.get(f"{GATEWAY_BASE}/health", timeout=2)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _server_alive(),
    reason=f"gateway smoke server not running at {GATEWAY_BASE}",
)


def test_openai_chat_completion_golden_path() -> None:
    """End-to-end: signup + login skipped (dev bearer), /v1/chat/completions
    returns OpenAI shape, trace + audit + usage rows are persisted.
    """
    payload = {
        "model": "fake-model",
        "messages": [{"role": "user", "content": "hi"}],
    }
    r = requests.post(
        f"{GATEWAY_BASE}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {DEV_BEARER}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "fake-model"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"]
    assert body["usage"]["prompt_tokens"] == 7
    assert body["usage"]["completion_tokens"] == 3

    # Allow the async TraceWriter drain (max ~1s flush_interval).
    eng = sa.create_engine(GATEWAY_DB_URL)
    deadline = time.monotonic() + 5.0
    trace_row = None
    while time.monotonic() < deadline:
        with eng.connect() as conn:
            trace_row = conn.execute(
                sa.text(
                    "SELECT route, status, model_requested, model_used, "
                    "provider, tokens_in, tokens_out "
                    "FROM request_traces "
                    "WHERE route = 'POST /v1/chat/completions' "
                    "ORDER BY ts DESC LIMIT 1"
                )
            ).first()
        if trace_row is not None:
            break
        time.sleep(0.25)

    assert trace_row is not None, "expected request_traces row, none written"
    assert trace_row.status == "ok"
    assert trace_row.model_requested == "fake-model"
    assert trace_row.provider == "fake"
    assert trace_row.tokens_in == 7
    assert trace_row.tokens_out == 3

    with eng.connect() as conn:
        usage_row = conn.execute(
            sa.text(
                "SELECT unit, module, model, qty FROM usage_events "
                "WHERE module = 'gateway' AND unit = 'tokens_in' "
                "ORDER BY ts DESC LIMIT 1"
            )
        ).first()
        audit_row = conn.execute(
            sa.text(
                "SELECT event_type, action FROM audit_events "
                "WHERE event_type LIKE 'gateway.%' "
                "ORDER BY created_at DESC LIMIT 1"
            )
        ).first()

    assert usage_row is not None, "expected usage_events row with tokens_in"
    assert usage_row.model == "fake-model"
    assert int(usage_row.qty) == 7

    assert audit_row is not None, "expected audit_events row for gateway.*"
    assert audit_row.event_type.startswith("gateway.")
