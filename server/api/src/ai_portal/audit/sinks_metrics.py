"""In-process metrics for audit sink health.

Records the most recent write outcome, error, and a sliding-window latency
sample for every (org_id, sink_name) pair. Designed to be cheap and lock-free
enough for the volumes we expect; bounded memory via a fixed-size deque.

Exposed shape (consumed by the /v1/audit/sinks/health and /metrics endpoints):

    {
        "org_id": "...",
        "sink": "splunk_hec",
        "last_write_at": "...",
        "last_error": "..." | null,
        "last_status": "ok" | "error",
        "samples": int,
        "success_rate": 0..1,
        "p50_latency_ms": float,
        "p95_latency_ms": float,
    }
"""

from __future__ import annotations

import math
import statistics
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

_WINDOW = 200  # samples retained per (org, sink)


@dataclass
class _SinkSeries:
    success_count: int = 0
    error_count: int = 0
    last_status: str = "unknown"
    last_error: str | None = None
    last_write_at: datetime | None = None
    latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=_WINDOW))


class SinkMetrics:
    """Thread-safe in-memory metrics. One instance per process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._series: dict[tuple[str, str], _SinkSeries] = {}

    def _key(self, org_id: uuid.UUID | str, sink_name: str) -> tuple[str, str]:
        return (str(org_id), sink_name)

    def record_success(
        self,
        org_id: uuid.UUID | str,
        sink_name: str,
        latency_ms: float,
        *,
        at: datetime | None = None,
    ) -> None:
        with self._lock:
            s = self._series.setdefault(self._key(org_id, sink_name), _SinkSeries())
            s.success_count += 1
            s.last_status = "ok"
            s.last_error = None
            s.last_write_at = at or datetime.now(UTC)
            s.latencies_ms.append(float(latency_ms))

    def record_error(
        self,
        org_id: uuid.UUID | str,
        sink_name: str,
        err: BaseException | str,
        *,
        at: datetime | None = None,
    ) -> None:
        with self._lock:
            s = self._series.setdefault(self._key(org_id, sink_name), _SinkSeries())
            s.error_count += 1
            s.last_status = "error"
            s.last_error = str(err) if not isinstance(err, BaseException) else f"{type(err).__name__}: {err}"
            s.last_write_at = at or datetime.now(UTC)

    def reset(self) -> None:
        with self._lock:
            self._series.clear()

    # ---- read helpers ----------------------------------------------------

    def _snapshot_series(self, s: _SinkSeries) -> dict:
        total = s.success_count + s.error_count
        success_rate = (s.success_count / total) if total else 1.0
        latencies = list(s.latencies_ms)
        p50 = _percentile(latencies, 50.0)
        p95 = _percentile(latencies, 95.0)
        return {
            "last_write_at": s.last_write_at.isoformat() if s.last_write_at else None,
            "last_status": s.last_status,
            "last_error": s.last_error,
            "samples": total,
            "success_count": s.success_count,
            "error_count": s.error_count,
            "success_rate": round(success_rate, 6),
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
        }

    def list_org(self, org_id: uuid.UUID | str) -> list[dict]:
        target = str(org_id)
        out: list[dict] = []
        with self._lock:
            for (oid, name), s in self._series.items():
                if oid != target:
                    continue
                snap = self._snapshot_series(s)
                snap.update({"org_id": oid, "sink": name})
                out.append(snap)
        out.sort(key=lambda r: r["sink"])
        return out


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 3)
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(s[int(k)], 3)
    return round(s[f] + (s[c] - s[f]) * (k - f), 3)


_default = SinkMetrics()


def metrics() -> SinkMetrics:
    """Return the per-process metrics singleton."""
    return _default


def record_write(
    org_id: uuid.UUID | str,
    sink_name: str,
    *,
    started_at: float,
    error: BaseException | None,
) -> None:
    """Convenience: compute latency from ``started_at`` (perf_counter)."""
    latency_ms = max(0.0, (time.perf_counter() - started_at) * 1000.0)
    if error is None:
        _default.record_success(org_id, sink_name, latency_ms)
    else:
        _default.record_error(org_id, sink_name, error)
