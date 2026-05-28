"""Phase L — GDPR delete + export adapter wiring."""
from __future__ import annotations

import inspect

from ai_portal.memory import gdpr


def test_delete_for_user_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(gdpr.delete_for_user)
    sig = inspect.signature(gdpr.delete_for_user)
    assert {"session", "org_id", "user_id"} <= set(sig.parameters)


def test_export_for_user_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(gdpr.export_for_user)


def test_register_runs_without_raising() -> None:
    # control_plane may or may not be wired in test env; should not raise.
    gdpr.register()


def test_adapter_signatures_match_protocol() -> None:
    delete_sig = inspect.signature(gdpr._delete_adapter)
    assert list(delete_sig.parameters) == ["org_id", "scope"]
    export_sig = inspect.signature(gdpr._export_adapter)
    assert list(export_sig.parameters) == ["org_id"]
