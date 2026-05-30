"""DirectoryProvider protocol — LDAP/AD bind interface.

Routes call ``authenticate`` with the credentials from the login form. The
provider service-binds, finds the user, re-binds as the user to verify the
password, then maps directory attributes + groups to :class:`UserClaims`.

``lookup`` resolves a directory entry without verifying a password (admin
tooling). ``test_connection`` checks the service-account bind for the admin UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ai_portal.auth.idp.protocol import UserClaims

__all__ = ["DirectoryEntry", "DirectoryProvider", "UserClaims"]


@dataclass(frozen=True, slots=True)
class DirectoryEntry:
    """A resolved directory record (no password verification)."""

    dn: str
    email: str | None
    display_name: str | None
    groups: tuple[str, ...] = ()
    attributes: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class DirectoryProvider(Protocol):
    """LDAP / Active Directory connection instance."""

    name: str

    def authenticate(self, *, username: str, password: str) -> UserClaims:
        """Bind as the user to verify the password; return mapped claims.

        Raises ``DirectoryAuthError`` on bad credentials and
        ``DirectoryConnectionError`` on transport/config failure.
        """
        ...

    def lookup(self, *, username: str) -> DirectoryEntry:
        """Resolve a directory entry without verifying a password."""
        ...

    def test_connection(self) -> bool:
        """Return True if the service-account bind succeeds."""
        ...
