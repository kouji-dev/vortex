"""ACL mirroring subsystem.

Captures source-system permissions during ingest, resolves connector-native
user/group identifiers to internal org users/groups via an IdP mapper,
stores the resulting allow set per document and per chunk in ``kb_acls``,
and exposes a server-side filter applied to retrieval so callers can never
see content they shouldn't.

Modules:

- :mod:`protocol` — ``AclProvider`` protocol + ``ResolvedAcl`` dataclass.
- :mod:`registry` — connector-kind → provider lookup.
- :mod:`idp_mapping` — best-effort mapper from source IDs to org IDs.
- :mod:`service` — capture + store + resync orchestration.
- :mod:`filter` — server-side ``actor in allow_set`` retrieval filter.
- :mod:`resync` — re-apply ACLs on connector ACL-change events.
"""

from ai_portal.rag.acl.filter import (
    build_allow_predicate,
    filter_hits,
    filter_hits_multi_kb,
)
from ai_portal.rag.acl.protocol import (
    AclProvider,
    ResolvedAcl,
)
from ai_portal.rag.acl.registry import (
    DuplicateAclProvider,
    UnknownAclProvider,
    get as get_provider,
    register as register_provider,
    registered_kinds,
)
from ai_portal.rag.acl.service import (
    capture_acls,
    delete_acl_for_document,
    fanout_to_chunks,
    store_document_acl,
    visible_chunk_ids,
    visible_document_ids,
)

__all__ = [
    "AclProvider",
    "DuplicateAclProvider",
    "ResolvedAcl",
    "UnknownAclProvider",
    "build_allow_predicate",
    "capture_acls",
    "delete_acl_for_document",
    "fanout_to_chunks",
    "filter_hits",
    "filter_hits_multi_kb",
    "get_provider",
    "register_provider",
    "registered_kinds",
    "store_document_acl",
    "visible_chunk_ids",
    "visible_document_ids",
]
