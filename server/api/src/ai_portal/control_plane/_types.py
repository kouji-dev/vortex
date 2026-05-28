"""Cross-cutting type aliases re-exported by the control-plane facade.

These are intentionally tiny; they exist so downstream modules can annotate
their public signatures with a name that is stable even if the underlying
enum / Literal evolves.
"""
from __future__ import annotations

from typing import Literal

from ai_portal.settings import KNOWN_MODULES

# Discriminated module label used by ``is_module_enabled``, ``set_module_flag``,
# the usage events table, and the webhooks routing rules.
ModuleName = Literal[
    "gateway",
    "rag",
    "memories",
    "workers",
    "assistants",
    "chat",
    "knowledge_base",
]

# Permission keys follow ``<namespace>:<action>(:<scope>)?``. Typed as ``str``
# to avoid drift with the catalog; ``ai_portal.rbac.catalog.PERMISSIONS`` is
# the authoritative list.
PermissionKey = str


__all__ = ["KNOWN_MODULES", "ModuleName", "PermissionKey"]
