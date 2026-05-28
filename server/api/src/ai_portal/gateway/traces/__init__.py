"""Gateway traces — request_traces writer + OTEL export."""

from ai_portal.gateway.traces.model import RequestTrace
from ai_portal.gateway.traces.writer import TraceRecord, TraceWriter, get_writer

__all__ = ["RequestTrace", "TraceRecord", "TraceWriter", "get_writer"]
