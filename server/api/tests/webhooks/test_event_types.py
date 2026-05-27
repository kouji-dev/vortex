"""webhooks.event_types — process-local registry."""

from __future__ import annotations

import pytest

from ai_portal.webhooks import event_types
from ai_portal.webhooks.event_types import (
    EventTypeAlreadyRegistered,
    is_registered,
    list_event_types,
    register_event_type,
)


def test_seed_event_types_registered() -> None:
    """Migration + module import seed the bundled control-plane event types."""
    for key in (
        "budget.exceeded",
        "budget.warning",
        "gateway.policy.violation",
        "usage.threshold",
        "org.member.added",
        "org.member.removed",
        "api_key.created",
        "api_key.revoked",
    ):
        assert is_registered(key), f"expected {key!r} to be seeded"


def test_register_event_type_returns_record() -> None:
    et = register_event_type(
        "test.x.unique-1",
        "test event",
        module="test",
    )
    assert et.key == "test.x.unique-1"
    assert et.module == "test"
    assert is_registered("test.x.unique-1")


def test_register_event_type_idempotent_for_same_shape() -> None:
    et1 = register_event_type("test.idem", "desc", module="m")
    et2 = register_event_type("test.idem", "desc", module="m")
    assert et1 == et2


def test_register_event_type_rejects_conflicting_redefinition() -> None:
    register_event_type("test.conflict", "original", module="m")
    with pytest.raises(EventTypeAlreadyRegistered):
        register_event_type("test.conflict", "different", module="m")


def test_register_event_type_rejects_empty_key() -> None:
    with pytest.raises(ValueError):
        register_event_type("", "x", module="m")


def test_register_event_type_rejects_oversized_key() -> None:
    with pytest.raises(ValueError):
        register_event_type("a" * 65, "x", module="m")


def test_list_event_types_sorted() -> None:
    all_types = list_event_types()
    keys = [e.key for e in all_types]
    assert keys == sorted(keys)


def test_registry_module_attribute_accessible() -> None:
    # Catalog is importable as a module-level constant for diagnostics.
    assert hasattr(event_types, "_REGISTRY")
