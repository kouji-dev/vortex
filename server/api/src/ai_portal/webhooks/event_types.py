"""Process-local registry of webhook event types.

Modules register their event types at import time:

    from ai_portal.webhooks import register_event_type
    register_event_type("budget.exceeded", "Org budget exceeded", module="budgets")

The registry is the source of truth for ``emit_webhook`` and for the admin UI
"available event types" dropdown. Migration seeds initial control-plane keys;
new entries are upserted into ``webhook_event_types`` on app startup by the
``sync_event_types_to_db`` helper.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EventType:
    key: str
    description: str
    module: str


class EventTypeAlreadyRegistered(Exception):
    """Raised on duplicate registration with a different shape."""


# Process-local registry. Keys are unique across modules.
_REGISTRY: dict[str, EventType] = {}


def register_event_type(key: str, description: str, *, module: str) -> EventType:
    """Register a webhook event type. Idempotent for identical re-registration."""
    if not key or not isinstance(key, str):
        raise ValueError("event type key required")
    if len(key) > 64:
        raise ValueError(f"event type key too long: {key!r}")
    existing = _REGISTRY.get(key)
    et = EventType(key=key, description=description, module=module)
    if existing is not None:
        if existing != et:
            raise EventTypeAlreadyRegistered(
                f"event type {key!r} already registered with different shape"
            )
        return existing
    _REGISTRY[key] = et
    return et


def is_registered(key: str) -> bool:
    return key in _REGISTRY


def get(key: str) -> EventType | None:
    return _REGISTRY.get(key)


def list_event_types() -> list[EventType]:
    """Return all registered event types, sorted by key."""
    return sorted(_REGISTRY.values(), key=lambda e: e.key)


def _reset_for_tests() -> None:  # pragma: no cover — test helper
    _REGISTRY.clear()


# ── Seed: control-plane bundled event types ──────────────────────────────────

register_event_type(
    "budget.exceeded",
    "Org budget hard limit reached; further calls blocked",
    module="budgets",
)
register_event_type(
    "budget.warning",
    "Org budget crossed a soft warning threshold (50/80/100%)",
    module="budgets",
)
register_event_type(
    "gateway.policy.violation",
    "Gateway policy denied a request",
    module="gateway",
)
register_event_type(
    "usage.threshold",
    "Configured usage threshold reached",
    module="usage",
)
register_event_type(
    "org.member.added",
    "A user was added to the org",
    module="orgs",
)
register_event_type(
    "org.member.removed",
    "A user was removed from the org",
    module="orgs",
)
register_event_type(
    "api_key.created",
    "A new API key was minted",
    module="api_keys",
)
register_event_type(
    "api_key.revoked",
    "An API key was revoked",
    module="api_keys",
)
