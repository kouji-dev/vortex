"""External web + internal search providers.

Each provider implements the ``SearchProvider`` protocol. The registry
resolves a provider by ``name`` (e.g. ``tavily``, ``exa``, ``brave``,
``bing``, ``google_cse``, ``internal_kbs``) and is used by the
``POST /v1/search`` route.
"""

from ai_portal.rag.search_providers.protocol import (
    SearchProvider,
    SearchProviderResult,
)
from ai_portal.rag.search_providers.registry import (
    get_provider,
    list_providers,
    register,
)

__all__ = [
    "SearchProvider",
    "SearchProviderResult",
    "get_provider",
    "list_providers",
    "register",
]
