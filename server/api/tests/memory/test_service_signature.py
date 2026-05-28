"""Phase G — MemoryService surface (no DB).

Validates that every public method is async + present, that the service
exposes the canonical names from the spec, and that ExtractResult fields
exist.
"""
from __future__ import annotations

import inspect

from ai_portal.memory.service import ExtractResult, MemoryService


PUBLIC_ASYNC_METHODS = {
    "extract",
    "recall",
    "attach_uses",
    "add_manual",
    "patch",
    "soft_delete",
    "restore",
    "bulk_delete",
    "pause",
    "resume",
    "export_for_user",
    "export_to_blob",
}


def test_service_async_surface() -> None:
    for name in PUBLIC_ASYNC_METHODS:
        attr = getattr(MemoryService, name, None)
        assert attr is not None, name
        assert inspect.iscoroutinefunction(attr), name


def test_service_constructor() -> None:
    sig = inspect.signature(MemoryService.__init__)
    assert "session" in sig.parameters
    assert "extractor_name" in sig.parameters
    assert "policy_name" in sig.parameters


def test_extract_result_defaults() -> None:
    r = ExtractResult()
    assert r.created == []
    assert r.updated == []
    assert r.skipped_sensitive == []
    assert r.skipped_dedup == []
    assert r.skipped_paused is False
    assert r.skipped_module_disabled is False
