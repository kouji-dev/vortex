"""ACL provider protocol.

A provider maps connector-native user/group ids (e.g. email, AAD oid,
Google group id, Slack channel member id) into internal org user/group
ids. Mapping is *best-effort*: unresolved source ids are kept on the
:class:`ResolvedAcl` so a later re-sync (after IdP catches up) can fill
them in without re-ingesting the document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ai_portal.rag.connectors.protocol import AclSet


@dataclass
class ResolvedAcl:
    """Allow set resolved against the org IdP.

    - ``user_ids`` / ``group_ids`` — internal IDs (strings — we keep them
      provider-neutral; callers stringify ints or UUIDs).
    - ``public`` — anyone in the org can read.
    - ``unresolved`` — source ids that could not be mapped. Kept for
      re-resolution by :mod:`ai_portal.rag.acl.resync`.
    """

    user_ids: set[str] = field(default_factory=set)
    group_ids: set[str] = field(default_factory=set)
    public: bool = False
    unresolved: set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        """True when no principal is allowed (deny-all)."""

        return (
            not self.public
            and not self.user_ids
            and not self.group_ids
        )


@runtime_checkable
class AclProvider(Protocol):
    """Maps connector-native ACL sets to org-internal allow sets.

    One provider per connector kind. Implementations are stateless — any
    IdP lookup state is injected at construction time.
    """

    connector_kind: str

    async def map(
        self, source_acls: AclSet, org_id: str
    ) -> ResolvedAcl:
        """Return the org-internal allow set for ``source_acls``."""
