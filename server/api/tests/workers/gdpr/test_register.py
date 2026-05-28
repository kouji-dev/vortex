"""Tests for the GDPR registration (no DB)."""

from __future__ import annotations

from ai_portal.workers.gdpr import register
from ai_portal.gdpr.registry import (
    clear_deleters,
    clear_exporters,
    get_deleter,
    get_exporter,
)


def test_register_installs_both_adapters() -> None:
    # clean slate to avoid relying on import-time side effects
    clear_deleters()
    clear_exporters()
    register()
    assert get_deleter("workers") is not None
    assert get_exporter("workers") is not None


def test_register_is_idempotent() -> None:
    register()
    first = get_deleter("workers")
    register()
    second = get_deleter("workers")
    # re-registration overwrites with the same module-level function
    assert first is second
