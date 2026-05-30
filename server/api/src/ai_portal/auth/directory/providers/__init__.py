"""Bundled directory providers — import to register them.

Registers the generic ``ldap`` provider and the ``active_directory`` preset.
``ldap3`` is imported lazily inside the provider, so this package imports
cleanly even when ``ldap3`` is not installed; the binding call raises a clear
error if the dependency is missing at runtime.
"""

from ai_portal.auth.directory.providers import (
    active_directory,  # noqa: F401
    ldap,  # noqa: F401
)
