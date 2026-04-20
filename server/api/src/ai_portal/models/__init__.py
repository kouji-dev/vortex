# Re-export shim — imports kept for backward compatibility while callers migrate.
# New code should import directly from the domain model module, e.g.:
#   from ai_portal.auth.model import User
#   from ai_portal.chat.model import Thread
from ai_portal.core.db.base import Base  # noqa: F401
from ai_portal.assistant.model import Assistant, AssistantAcl  # noqa: F401
from ai_portal.catalog.model import CatalogModel  # noqa: F401
from ai_portal.chat.model import Thread, ThreadItem  # noqa: F401
from ai_portal.memory.model import UserMemory  # noqa: F401
from ai_portal.knowledge_base.model import (  # noqa: F401
    ConnectorSyncJob,
    ConversationKnowledgeBase,
    Document,
    DocumentChunk,
    KnowledgeBase,
    KnowledgeBaseConnector,
)
from ai_portal.auth.model import Org, OrgInvite, User, UserPortalApiKey  # noqa: F401

__all__ = [
    "Assistant",
    "AssistantAcl",
    "Base",
    "CatalogModel",
    "Thread",
    "ThreadItem",
    "ConnectorSyncJob",
    "ConversationKnowledgeBase",
    "Document",
    "DocumentChunk",
    "KnowledgeBase",
    "KnowledgeBaseConnector",
    "Org",
    "OrgInvite",
    "User",
    "UserMemory",
    "UserPortalApiKey",
]
