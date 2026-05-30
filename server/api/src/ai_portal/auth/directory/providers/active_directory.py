"""Active Directory preset.

AD is LDAP-based. This preset only changes defaults: the user filter targets
``sAMAccountName`` and the attribute map uses AD's canonical names. Everything
else (bind, re-bind, group→role) is inherited from :class:`LdapProvider`.
"""

from __future__ import annotations

from typing import Any

from ai_portal.auth.directory.providers.ldap import LdapProvider
from ai_portal.auth.directory.registry import register_directory_provider

_AD_ATTR_MAP = {
    "email": "mail",
    "name": "displayName",
    "groups": "memberOf",
}


class ActiveDirectoryProvider(LdapProvider):
    name = "active_directory"
    default_user_filter = "(sAMAccountName={username})"

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ActiveDirectoryProvider:
        merged = dict(config)
        merged.setdefault("user_filter", cls.default_user_filter)
        attr_map = {**_AD_ATTR_MAP, **(config.get("attr_map") or {})}
        merged["attr_map"] = attr_map
        # Reuse the base validation + construction.
        base = LdapProvider.from_config(merged)
        return cls(
            host=base.host,
            port=base.port,
            bind_dn=base.bind_dn,
            bind_secret=base.bind_secret,
            base_dn=base.base_dn,
            user_filter=base.user_filter,
            group_filter=base.group_filter,
            tls_mode=base.tls_mode,
            attr_map=base.attr_map,
            group_role_map=base.group_role_map,
        )


register_directory_provider("active_directory", ActiveDirectoryProvider.from_config)
