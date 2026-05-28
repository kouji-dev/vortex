"""OTEL gateway export — emit_span attaches canonical attributes."""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry")
pytest.importorskip("opentelemetry.sdk")


def test_install_idempotent():
    from ai_portal.gateway.traces import otel

    otel.reset_for_tests()
    otel.install(test_mode=True)
    otel.install(test_mode=True)  # should not raise
    assert otel.get_test_exporter() is not None


def test_emit_span_records_canonical_attributes():
    from ai_portal.gateway.traces import otel

    otel.reset_for_tests()
    otel.install(test_mode=True)

    otel.emit_span(
        route="/v1/chat/completions",
        model_requested="claude-sonnet-4-6",
        model_used="claude-sonnet-4-6-20260101",
        provider="anthropic",
        status="ok",
        latency_ms=842,
        ttft_ms=210,
        tokens_in=1200,
        tokens_out=350,
        tokens_cache_read=900,
        tokens_cache_write=300,
        cost_cents=4.25,
        cache_hit=True,
    )

    exporter = otel.get_test_exporter()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "gateway.request"
    attrs = dict(span.attributes)
    assert attrs["gateway.route"] == "/v1/chat/completions"
    assert attrs["gateway.model_requested"] == "claude-sonnet-4-6"
    assert attrs["gateway.model_used"] == "claude-sonnet-4-6-20260101"
    assert attrs["gateway.provider"] == "anthropic"
    assert attrs["gateway.status"] == "ok"
    assert attrs["gateway.latency_ms"] == 842
    assert attrs["gateway.ttft_ms"] == 210
    assert attrs["gateway.tokens_in"] == 1200
    assert attrs["gateway.tokens_out"] == 350
    assert attrs["gateway.tokens_cache_read"] == 900
    assert attrs["gateway.tokens_cache_write"] == 300
    assert attrs["gateway.cost_cents"] == pytest.approx(4.25)
    assert attrs["gateway.cache_hit"] is True


def test_emit_span_error_sets_error_status():
    from ai_portal.gateway.traces import otel

    otel.reset_for_tests()
    otel.install(test_mode=True)

    otel.emit_span(
        route="/v1/messages",
        provider="anthropic",
        status="error",
        error="rate_limit",
    )

    spans = otel.get_test_exporter().get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    attrs = dict(span.attributes)
    assert attrs["gateway.status"] == "error"
    assert attrs["gateway.error"] == "rate_limit"
    # OTEL status should be ERROR
    from opentelemetry.trace import StatusCode  # noqa: PLC0415

    assert span.status.status_code == StatusCode.ERROR


def test_is_enabled_reads_env(monkeypatch):
    from ai_portal.gateway.traces import otel

    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    assert otel.is_enabled() is False
    monkeypatch.setenv("OTEL_ENABLED", "1")
    assert otel.is_enabled() is True
    monkeypatch.setenv("OTEL_ENABLED", "true")
    assert otel.is_enabled() is True
    monkeypatch.setenv("OTEL_ENABLED", "false")
    assert otel.is_enabled() is False
