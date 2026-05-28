"""OpenTelemetry export for gateway traces.

Install OTEL provider on app startup (gated by ``OTEL_ENABLED``).
Emit one span per gateway request with canonical attributes.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_installed = False
_tracer = None
_provider = None
_test_exporter = None  # In-memory exporter for tests.


def is_enabled() -> bool:
    return os.environ.get("OTEL_ENABLED", "").lower() in ("1", "true", "yes")


def install(
    *,
    service_name: str = "ai-portal-gateway",
    endpoint: str | None = None,
    test_mode: bool = False,
) -> None:
    """Install OTEL TracerProvider once. Idempotent.

    ``test_mode`` swaps the OTLP exporter for an in-memory one so tests can
    assert on spans without a collector.
    """
    global _installed, _tracer, _provider, _test_exporter
    if _installed:
        return

    try:
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import (  # noqa: PLC0415
            BatchSpanProcessor,
            SimpleSpanProcessor,
        )
    except ImportError as exc:
        logger.warning("otel_install_skipped: %s", exc)
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if test_mode:
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: PLC0415
            InMemorySpanExporter,
        )

        _test_exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(_test_exporter))
    else:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
                OTLPSpanExporter,
            )

            otlp_endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
            exporter = (
                OTLPSpanExporter(endpoint=otlp_endpoint)
                if otlp_endpoint
                else OTLPSpanExporter()
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception as exc:  # noqa: BLE001
            logger.warning("otel_otlp_exporter_unavailable: %s", exc)

    # Set global only once per process; subsequent installs (e.g. tests) use
    # the provider directly without touching the global.
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # noqa: BLE001
        pass
    _provider = provider
    _tracer = provider.get_tracer("ai_portal.gateway")
    _installed = True


def get_tracer() -> Any:
    global _tracer, _provider
    if _tracer is not None:
        return _tracer
    if _provider is not None:
        _tracer = _provider.get_tracer("ai_portal.gateway")
        return _tracer
    from opentelemetry import trace  # noqa: PLC0415

    _tracer = trace.get_tracer("ai_portal.gateway")
    return _tracer


def get_test_exporter() -> Any:
    """Return the in-memory exporter installed via ``install(test_mode=True)``."""
    return _test_exporter


def reset_for_tests() -> None:
    """Reset OTEL singletons for tests."""
    global _installed, _tracer, _provider, _test_exporter
    _installed = False
    _tracer = None
    _provider = None
    _test_exporter = None


def emit_span(
    *,
    route: str,
    model_requested: str | None = None,
    model_used: str | None = None,
    provider: str | None = None,
    status: str = "ok",
    latency_ms: int | None = None,
    ttft_ms: int | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    tokens_cache_read: int = 0,
    tokens_cache_write: int = 0,
    cost_cents: float = 0.0,
    cache_hit: bool = False,
    error: str | None = None,
) -> None:
    """Emit one gateway span. No-op if OTEL not installed."""
    try:
        tracer = get_tracer()
    except Exception:  # noqa: BLE001
        return
    if tracer is None:
        return
    attrs: dict[str, Any] = {
        "gateway.route": route,
        "gateway.status": status,
        "gateway.tokens_in": tokens_in,
        "gateway.tokens_out": tokens_out,
        "gateway.tokens_cache_read": tokens_cache_read,
        "gateway.tokens_cache_write": tokens_cache_write,
        "gateway.cost_cents": cost_cents,
        "gateway.cache_hit": cache_hit,
    }
    if model_requested:
        attrs["gateway.model_requested"] = model_requested
    if model_used:
        attrs["gateway.model_used"] = model_used
    if provider:
        attrs["gateway.provider"] = provider
    if latency_ms is not None:
        attrs["gateway.latency_ms"] = latency_ms
    if ttft_ms is not None:
        attrs["gateway.ttft_ms"] = ttft_ms
    if error:
        attrs["gateway.error"] = error

    with tracer.start_as_current_span("gateway.request", attributes=attrs) as span:
        if status != "ok":
            try:
                from opentelemetry.trace import Status, StatusCode  # noqa: PLC0415

                span.set_status(Status(StatusCode.ERROR, description=error or status))
            except Exception:  # noqa: BLE001
                pass
