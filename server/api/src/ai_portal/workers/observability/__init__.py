"""Worker observability — trace correlation, replay metadata, metrics tags.

Workers run inside the Gateway: every LLM call produces a ``RequestTrace``
row. To correlate, the worker tags each Gateway request with
``{"task_id": ..., "run_id": ...}`` in the actor metadata. This module
provides:

- :func:`build_trace_actor` — canonical actor-dict shape with task_id/run_id.
- :func:`task_id_filter` — SQLAlchemy filter snippet to query traces by task.
- :func:`metric_tags` — labels for prom-style metrics.
"""

from ai_portal.workers.observability.trace_link import (
    build_trace_actor,
    task_id_filter,
    metric_tags,
    extract_task_id,
)

__all__ = [
    "build_trace_actor",
    "task_id_filter",
    "metric_tags",
    "extract_task_id",
]
