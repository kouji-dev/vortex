"""Bundled IdP provider implementations.

Each bundled module registers itself in the global IdP registry via
:func:`ai_portal.auth.idp.registry.register_provider` at import time. Apps
that want SSO must import this package once during startup.
"""
