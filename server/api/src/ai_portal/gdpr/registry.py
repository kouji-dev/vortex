"""Module registries for GDPR participation.

Process-global dict, keyed by module name:

- ``_EXPORTERS``: ``module_name -> async fn(org_id: UUID) -> dict``

Modules call :func:`register_exporter` at import time. The export worker
iterates the registry to fan out a job.

Re-registering the same key overwrites the previous entry — tests and the
production startup path rely on idempotent registration.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Awaitable, Callable

Exporter = Callable[[_uuid.UUID], Awaitable[dict]]


_EXPORTERS: dict[str, Exporter] = {}


# ── Exporters ───────────────────────────────────────────────────────────────


def register_exporter(module_name: str, fn: Exporter) -> None:
    """Register ``fn`` as the exporter for ``module_name``.

    ``fn(org_id) -> dict`` must return a JSON-serialisable mapping. The
    worker writes one ``<module_name>.json`` file per registered exporter
    into the export zip.
    """
    _EXPORTERS[module_name] = fn


def get_exporter(module_name: str) -> Exporter | None:
    return _EXPORTERS.get(module_name)


def list_exporters() -> dict[str, Exporter]:
    """Return a shallow copy of the exporter registry."""
    return dict(_EXPORTERS)


def clear_exporters() -> None:
    """Test helper — wipe the registry."""
    _EXPORTERS.clear()
