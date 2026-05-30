"""Deployment auth-config — declares which auth strategies are enabled.

Config-driven, not mode-gated: a deployment turns strategies on/off via env
(or YAML), and the frontend renders only those. There is NO ``saas`` /
``selfhosted`` switch in code paths.

Public surface:
- :func:`get_auth_config` — load the current :class:`AuthConfig`.
- :func:`get_enabled_auth_strategies` — module-boundary alias used by other code.
"""

from ai_portal.auth.config.loader import (
    AuthConfig,
    get_auth_config,
    get_enabled_auth_strategies,
    reset_cache,
)

__all__ = [
    "AuthConfig",
    "get_auth_config",
    "get_enabled_auth_strategies",
    "reset_cache",
]
