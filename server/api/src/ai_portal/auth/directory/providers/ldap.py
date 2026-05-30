"""Generic LDAP v3 directory provider (real bind via ``ldap3``).

Flow:
1. Bind with the service account (``bind_dn`` / ``bind_secret``).
2. Search ``base_dn`` with ``user_filter`` ({username} substituted) to find the
   user's DN + attributes.
3. Re-bind as that DN with the supplied password to verify it.
4. Read groups from ``memberOf`` (or a group search) and map attributes.

Transport: ``tls_mode`` ∈ {``none``, ``starttls``, ``ldaps``}. ``ldaps`` uses
an SSL socket; ``starttls`` upgrades a plain connection.

``ldap3`` is imported lazily so importing this module never requires the
package; a missing dependency surfaces as :class:`DirectoryConnectionError`.

Config keys:
- ``host`` (required), ``port`` (default 389 / 636 for ldaps)
- ``bind_dn``, ``bind_secret`` (service account; both required)
- ``base_dn`` (required), ``user_filter`` (default ``(uid={username})``)
- ``group_filter`` (optional), ``tls_mode`` (default ``none``)
- ``attr_map`` (dict: email/name/groups attribute names)
- ``group_role_map`` (dict: directory group → RBAC role)
"""

from __future__ import annotations

from typing import Any

from ai_portal.auth.directory.protocol import DirectoryEntry
from ai_portal.auth.directory.registry import register_directory_provider
from ai_portal.auth.idp.protocol import UserClaims


class DirectoryError(Exception):
    """Base directory failure."""


class DirectoryConnectionError(DirectoryError):
    """Transport/config failure (host unreachable, ldap3 missing, bad bind DN)."""


class DirectoryAuthError(DirectoryError):
    """Credentials rejected by the directory."""


_DEFAULT_ATTR_MAP = {
    "email": "mail",
    "name": "displayName",
    "groups": "memberOf",
}


def _import_ldap3():
    try:
        import ldap3  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise DirectoryConnectionError(
            "ldap3 is not installed — add 'ldap3' to run directory auth"
        ) from exc
    return ldap3


class LdapProvider:
    """Generic LDAP v3 bind provider."""

    name = "ldap"
    default_user_filter = "(uid={username})"

    def __init__(
        self,
        *,
        host: str,
        port: int | None = None,
        bind_dn: str,
        bind_secret: str,
        base_dn: str,
        user_filter: str | None = None,
        group_filter: str | None = None,
        tls_mode: str = "none",
        attr_map: dict[str, str] | None = None,
        group_role_map: dict[str, str] | None = None,
    ) -> None:
        self.host = host
        self.tls_mode = (tls_mode or "none").lower()
        self.port = port or (636 if self.tls_mode == "ldaps" else 389)
        self.bind_dn = bind_dn
        self.bind_secret = bind_secret
        self.base_dn = base_dn
        self.user_filter = user_filter or self.default_user_filter
        self.group_filter = group_filter
        self.attr_map = {**_DEFAULT_ATTR_MAP, **(attr_map or {})}
        self.group_role_map = group_role_map or {}

    # ── factory ──────────────────────────────────────────────────────────
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> LdapProvider:
        missing = [
            k for k in ("host", "bind_dn", "bind_secret", "base_dn")
            if not config.get(k)
        ]
        if missing:
            raise DirectoryConnectionError(f"ldap config missing keys: {missing}")
        return cls(
            host=config["host"],
            port=config.get("port"),
            bind_dn=config["bind_dn"],
            bind_secret=config["bind_secret"],
            base_dn=config["base_dn"],
            user_filter=config.get("user_filter"),
            group_filter=config.get("group_filter"),
            tls_mode=config.get("tls_mode", "none"),
            attr_map=config.get("attr_map"),
            group_role_map=config.get("group_role_map"),
        )

    # ── ldap3 plumbing ───────────────────────────────────────────────────
    def _server(self):
        ldap3 = _import_ldap3()
        use_ssl = self.tls_mode == "ldaps"
        return ldap3.Server(self.host, port=self.port, use_ssl=use_ssl, get_info=None)

    def _service_conn(self):
        ldap3 = _import_ldap3()
        server = self._server()
        conn = ldap3.Connection(
            server, user=self.bind_dn, password=self.bind_secret, read_only=True
        )
        if self.tls_mode == "starttls":
            conn.open()
            conn.start_tls()
        if not conn.bind():
            raise DirectoryConnectionError(
                f"service bind failed: {conn.result.get('description', 'unknown')}"
            )
        return conn

    def _attr_list(self) -> list[str]:
        return [self.attr_map["email"], self.attr_map["name"], self.attr_map["groups"]]

    def _find_entry(self, conn, username: str):
        search_filter = self.user_filter.replace("{username}", _escape(username))
        conn.search(
            self.base_dn,
            search_filter,
            attributes=self._attr_list(),
        )
        if not conn.entries:
            return None
        return conn.entries[0]

    def _entry_to_directory(self, entry) -> DirectoryEntry:
        def _val(attr: str):
            try:
                return entry[attr].value
            except (KeyError, Exception):  # noqa: BLE001
                return None

        groups_raw = _val(self.attr_map["groups"]) or []
        if isinstance(groups_raw, str):
            groups_raw = [groups_raw]
        groups = tuple(str(g) for g in groups_raw)
        email = _val(self.attr_map["email"])
        name = _val(self.attr_map["name"])
        return DirectoryEntry(
            dn=str(entry.entry_dn),
            email=str(email) if email else None,
            display_name=str(name) if name else None,
            groups=groups,
        )

    # ── public protocol surface ──────────────────────────────────────────
    def authenticate(self, *, username: str, password: str) -> UserClaims:
        if not password:
            raise DirectoryAuthError("empty password")
        ldap3 = _import_ldap3()
        conn = self._service_conn()
        try:
            entry = self._find_entry(conn, username)
            if entry is None:
                raise DirectoryAuthError("user not found")
            directory = self._entry_to_directory(entry)
        finally:
            conn.unbind()

        # Re-bind as the user to verify the password.
        server = self._server()
        user_conn = ldap3.Connection(server, user=directory.dn, password=password)
        if self.tls_mode == "starttls":
            user_conn.open()
            user_conn.start_tls()
        if not user_conn.bind():
            raise DirectoryAuthError("invalid credentials")
        user_conn.unbind()

        roles = self.map_groups_to_roles(directory.groups)
        return UserClaims(
            subject=directory.dn,
            email=directory.email or "",
            name=directory.display_name,
            groups=directory.groups,
            raw={"roles": roles, "dn": directory.dn},
        )

    def lookup(self, *, username: str) -> DirectoryEntry:
        conn = self._service_conn()
        try:
            entry = self._find_entry(conn, username)
            if entry is None:
                raise DirectoryAuthError("user not found")
            return self._entry_to_directory(entry)
        finally:
            conn.unbind()

    def test_connection(self) -> bool:
        conn = self._service_conn()
        try:
            return bool(conn.bound)
        finally:
            conn.unbind()

    # ── group → role mapping ─────────────────────────────────────────────
    def map_groups_to_roles(self, groups: tuple[str, ...]) -> list[str]:
        """Resolve directory groups to RBAC role names via ``group_role_map``.

        Matching is case-insensitive and tolerates either a full DN
        (``cn=admins,...``) or a bare group name as the map key.
        """
        if not self.group_role_map:
            return []
        roles: list[str] = []
        lowered = {g.lower(): g for g in groups}
        for grp_key, role in self.group_role_map.items():
            key = grp_key.lower()
            matched = key in lowered or any(
                key == _cn_of(g) for g in lowered
            )
            if matched and role not in roles:
                roles.append(role)
        return roles


def _escape(value: str) -> str:
    """Escape LDAP filter special chars (RFC 4515)."""
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\5c")
        elif ch == "*":
            out.append("\\2a")
        elif ch == "(":
            out.append("\\28")
        elif ch == ")":
            out.append("\\29")
        elif ch == "\x00":
            out.append("\\00")
        else:
            out.append(ch)
    return "".join(out)


def _cn_of(dn: str) -> str:
    """Extract the lowercased CN value from a DN, or return the input."""
    for part in dn.split(","):
        part = part.strip()
        if part.lower().startswith("cn="):
            return part[3:].lower()
    return dn.lower()


register_directory_provider("ldap", LdapProvider.from_config)
