"""Connector manifest — static, side-effect-free description of a connector.

A manifest lets the framework reason about a connector without instantiating
it. The UI uses it to render auth+schedule controls; the orchestrator uses it
to decide whether to schedule or wait for webhooks.

Manifests are immutable: build once at module import, never mutate at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConnectorManifest:
    """Static description of a connector kind.

    - ``name``              — registry key (also the value stored in
      ``kb_connectors.kind``).
    - ``auth_kinds``        — tuple of supported auth modes. Recognised tokens:
      ``"none"``, ``"basic"``, ``"token"``, ``"oauth"``, ``"service_principal"``.
    - ``schedulable``       — can be cron-triggered (vs. webhook-only).
    - ``supports_delta``    — yields incremental cursors on ``discover``.
    - ``supports_acl``      — emits non-empty :class:`AclSet` from ``acls``.
    - ``supports_webhook``  — exposes a webhook handler for push-mode sync.
    - ``config_schema``     — JSON Schema (draft 2020-12) for the per-connector
      config blob. The orchestrator validates input against it before
      ``setup()`` is called.
    """

    name: str
    auth_kinds: tuple[str, ...]
    schedulable: bool
    supports_delta: bool
    supports_acl: bool
    supports_webhook: bool
    config_schema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:  # pragma: no cover - trivial guard
        if not self.name:
            raise ValueError("ConnectorManifest.name must be non-empty")
        if not self.auth_kinds:
            raise ValueError("ConnectorManifest.auth_kinds must be non-empty")
