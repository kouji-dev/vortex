"""RAG connectors subpackage.

A connector is a configurable source of documents. Each implementation:

- declares a :class:`ConnectorManifest` (auth kinds, schedulable, deltas, ACL, webhooks)
- conforms to the :class:`Connector` protocol (``setup`` → ``discover`` → ``fetch`` → ``acls``)
- registers itself by name in :func:`registry.register`

Public surface is intentionally narrow — downstream code never instantiates a
connector directly, it goes through :func:`registry.get`.
"""

from __future__ import annotations

from ai_portal.rag.connectors.manifest import ConnectorManifest
from ai_portal.rag.connectors.protocol import (
    AclSet,
    Connector,
    FetchedDoc,
    SourceDoc,
)
from ai_portal.rag.connectors.registry import (
    DuplicateConnector,
    UnknownConnector,
    get,
    register,
    registered_names,
)

__all__ = [
    "AclSet",
    "Connector",
    "ConnectorManifest",
    "DuplicateConnector",
    "FetchedDoc",
    "SourceDoc",
    "UnknownConnector",
    "get",
    "register",
    "registered_names",
]
