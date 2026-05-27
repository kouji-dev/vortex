"""Audit sink registry — kind→sink construction + per-org resolution."""

from __future__ import annotations

import pytest

from ai_portal.audit.registry import build_sink, resolve_sinks_for_org


def test_build_sink_splunk_returns_splunk_sink() -> None:
    from ai_portal.audit.sinks.splunk_hec import SplunkHecAuditSink
    sink = build_sink("splunk_hec", {"url": "https://splunk.example.com:8088", "token": "x"})
    assert isinstance(sink, SplunkHecAuditSink)
    assert sink.name == "splunk_hec"


def test_build_sink_datadog_returns_datadog_sink() -> None:
    from ai_portal.audit.sinks.datadog_logs import DatadogLogsAuditSink
    sink = build_sink("datadog_logs", {"api_key": "k"})
    assert isinstance(sink, DatadogLogsAuditSink)
    assert sink.name == "datadog_logs"


def test_build_sink_unknown_raises() -> None:
    with pytest.raises(ValueError):
        build_sink("not-a-real-sink", {})


def test_resolve_sinks_for_org_skips_invalid_entries() -> None:
    configs = [
        {"kind": "splunk_hec", "config": {"url": "https://x", "token": "t"}},
        {"kind": "not-a-real-sink", "config": {}},
        {"kind": "datadog_logs", "config": {"api_key": "k"}},
    ]
    sinks = resolve_sinks_for_org(configs)
    names = [s.name for s in sinks]
    assert names == ["splunk_hec", "datadog_logs"]


def test_resolve_sinks_empty_returns_empty() -> None:
    assert resolve_sinks_for_org([]) == []
    assert resolve_sinks_for_org(None) == []  # type: ignore[arg-type]
