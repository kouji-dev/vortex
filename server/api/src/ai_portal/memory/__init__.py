"""Memory module — public facade for cross-module imports.

Importing this package eagerly:
- registers bundled extractors / recallers / stores / policies
- attempts to register the GDPR delete + export adapters with the control
  plane (best-effort; silent when control-plane isn't wired)

Downstream modules (chat, assistants, workers, RAG) should import from
``ai_portal.memory`` only — never from sub-packages directly.
"""
from __future__ import annotations

# Eagerly import sub-packages so registries are populated on import.
from ai_portal.memory import (  # noqa: F401
    extractors,
    recallers,
    stores,
    policies,
)

from ai_portal.memory.extractors import get as get_extractor  # noqa: F401
from ai_portal.memory.extractors import list_names as list_extractors  # noqa: F401
from ai_portal.memory.extractors import register as register_extractor  # noqa: F401
from ai_portal.memory.recallers import get as get_recaller  # noqa: F401
from ai_portal.memory.recallers import list_names as list_recallers  # noqa: F401
from ai_portal.memory.recallers import register as register_recaller  # noqa: F401
from ai_portal.memory.stores import get as get_store  # noqa: F401
from ai_portal.memory.stores import list_names as list_stores  # noqa: F401
from ai_portal.memory.stores import register as register_store  # noqa: F401
from ai_portal.memory.policies import get as get_policy  # noqa: F401
from ai_portal.memory.policies import list_names as list_policies  # noqa: F401
from ai_portal.memory.policies import register as register_policy  # noqa: F401

# Deploy-vs-runtime provider config (declared SET → runtime selects from it).
from ai_portal.memory.deploy_config import (  # noqa: F401
    EnabledProviders,
    ProviderNotDeclared,
    default_for as default_provider,
    enabled_providers,
    is_enabled as provider_enabled,
    list_enabled as list_enabled_providers,
    validate_selection as validate_provider,
)

from ai_portal.memory.schemas import (  # noqa: F401
    BulkDeleteRequest,
    ExtractionPolicyDTO,
    ExtractRequest,
    MemoryCreate,
    MemoryOut,
    MemoryPatch,
    PauseRequest,
    RecallPolicyDTO,
    RecallRequest,
    RecallResult,
)

from ai_portal.memory.service import ExtractResult, MemoryService  # noqa: F401

from ai_portal.memory import integrations  # noqa: F401
from ai_portal.memory import rag_tool  # noqa: F401

# Best-effort GDPR + RAG tool registration. Silently no-ops outside the
# full app process (tests, alembic, etc.).
try:
    from ai_portal.memory import gdpr as _gdpr  # noqa: F401

    _gdpr.register()
except Exception:  # pragma: no cover
    pass
try:
    rag_tool.register_with_rag()
except Exception:  # pragma: no cover
    pass


__all__ = [
    "ExtractResult",
    "MemoryService",
    "MemoryOut",
    "MemoryCreate",
    "MemoryPatch",
    "BulkDeleteRequest",
    "RecallRequest",
    "RecallResult",
    "ExtractRequest",
    "ExtractionPolicyDTO",
    "RecallPolicyDTO",
    "PauseRequest",
    "get_extractor",
    "list_extractors",
    "register_extractor",
    "get_recaller",
    "list_recallers",
    "register_recaller",
    "get_store",
    "list_stores",
    "register_store",
    "get_policy",
    "list_policies",
    "register_policy",
    "EnabledProviders",
    "ProviderNotDeclared",
    "default_provider",
    "enabled_providers",
    "provider_enabled",
    "list_enabled_providers",
    "validate_provider",
    "integrations",
    "rag_tool",
]
