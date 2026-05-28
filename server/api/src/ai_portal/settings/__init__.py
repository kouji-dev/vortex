"""Settings + module flags domain.

Provides per-org KV settings and per-module enable/disable toggles.

Public surface:
- :func:`get_org_setting` / :func:`set_org_setting` — generic KV.
- :func:`is_module_enabled` / :func:`set_module_flag` — per-module on/off.
- :func:`get_feature_gate` / :func:`set_feature_gate` — per-module gates.
- :func:`assert_module_enabled` — FastAPI dep factory (503 if disabled).
"""
from __future__ import annotations

from ai_portal.settings.service import (  # noqa: F401
    KNOWN_MODULES,
    get_feature_gate,
    get_org_setting,
    is_module_enabled,
    set_feature_gate,
    set_module_flag,
    set_org_setting,
)
from ai_portal.settings.deps import assert_module_enabled  # noqa: F401

__all__ = [
    "KNOWN_MODULES",
    "assert_module_enabled",
    "get_feature_gate",
    "get_org_setting",
    "is_module_enabled",
    "set_feature_gate",
    "set_module_flag",
    "set_org_setting",
]
