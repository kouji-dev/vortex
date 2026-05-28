"""Module registries for GDPR participation.

Two process-global dicts, keyed by module name:

- ``_EXPORTERS``: ``module_name -> async fn(org_id: UUID) -> dict``
- ``_DELETERS``:  ``module_name -> async fn(org_id: UUID, scope: dict) -> None``

Modules call :func:`register_exporter` / :func:`register_deleter` at import
time. The workers iterate the registry to fan out a job.

Re-registering the same key overwrites the previous entry — tests and the
production startup path rely on idempotent registration.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Awaitable, Callable

Exporter = Callable[[_uuid.UUID], Awaitable[dict]]
Deleter = Callable[[_uuid.UUID, dict], Awaitable[None]]


_EXPORTERS: dict[str, Exporter] = {}
_DELETERS: dict[str, Deleter] = {}


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


# ── Deleters ────────────────────────────────────────────────────────────────


def register_deleter(module_name: str, fn: Deleter) -> None:
    """Register ``fn`` as the cascade deleter for ``module_name``.

    ``fn(org_id, scope)`` must hard-delete every row owned by the subject
    described in ``scope``. Idempotent — re-runs after partial failure must
    succeed without raising.
    """
    _DELETERS[module_name] = fn


def get_deleter(module_name: str) -> Deleter | None:
    return _DELETERS.get(module_name)


def list_deleters() -> dict[str, Deleter]:
    return dict(_DELETERS)


def clear_deleters() -> None:
    _DELETERS.clear()
