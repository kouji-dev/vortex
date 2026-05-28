"""Connector protocol — uniform surface for every data source.

A connector goes through three phases on every sync:

1. ``setup(config, secret_store)``  → instantiate from validated config.
2. ``discover(cursor)``               → async-iterate :class:`SourceDoc` refs.
3. for each ref → ``fetch(sd)``       → return bytes + mime + meta.

Delta sync is opt-in: implementations that support it persist a
``cursor_token`` on each :class:`SourceDoc` *and* track a single
:meth:`delta_cursor` that is replayed on the next run via
:meth:`apply_delta_cursor`.

ACL mirroring is opt-in: implementations that can map per-doc permissions
return a populated :class:`AclSet` from :meth:`acls`. The default contract
is ``public=True`` (everyone can read) — only safe for inherently public
sources like the web crawler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from ai_portal.rag.connectors.manifest import ConnectorManifest


@dataclass
class SourceDoc:
    """A *reference* to a document in the source system.

    Discovered cheaply (list endpoints, sitemap entries, etc.). The actual
    bytes are only loaded by :meth:`Connector.fetch`.

    - ``source_uri`` — canonical identifier in the source system (URL, object
      key, GDrive file id, Sharepoint drive-item id, ...). Globally unique
      within the connector.
    - ``cursor_token`` — per-doc delta cursor (lastmod, etag, generation).
      The orchestrator stores the max of these on success for the next run.
    - ``raw`` — passthrough for connector-native metadata.
    """

    source_uri: str
    title: str
    mime: str | None
    size: int | None
    modified_at: datetime | None
    cursor_token: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchedDoc:
    """Bytes + mime + meta returned by :meth:`Connector.fetch`."""

    data: bytes
    mime: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class AclSet:
    """Resolved set of principals allowed to read a source doc.

    The values are connector-native identifiers (email, AAD oid, Google
    group id, ...). The ACL mapper in ``rag/acl/`` resolves them to org
    users/groups before storage.
    """

    user_ids: set[str] = field(default_factory=set)
    group_ids: set[str] = field(default_factory=set)
    public: bool = False


@runtime_checkable
class Connector(Protocol):
    """Connector contract.

    Implementations expose a class-level ``manifest`` attribute and an async
    ``setup`` classmethod. They MUST be safe to instantiate without network
    I/O (network happens in ``setup`` or later).
    """

    manifest: ConnectorManifest

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "Connector":
        """Construct from validated config. May open clients / load creds."""

    def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        """Yield document references. Honors ``cursor`` for delta sync."""

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        """Return bytes + mime + meta for a source doc reference."""

    async def acls(self, sd: SourceDoc) -> AclSet:
        """Return the resolved ACL for a source doc."""

    async def delta_cursor(self) -> str | None:
        """Return the current delta cursor (highest seen)."""

    async def apply_delta_cursor(self, cursor: str) -> None:
        """Restore a previously persisted delta cursor."""
