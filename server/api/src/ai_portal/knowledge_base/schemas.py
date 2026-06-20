from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10_000)


class KnowledgeBaseRead(BaseModel):
    id: int
    name: str
    description: str
    owner_user_id: int
    created_at: object
    document_count: int | None = None
    chunks_count: int | None = None
    size_bytes: int | None = None

    model_config = {"from_attributes": True}


class KnowledgeBasePage(BaseModel):
    items: list[KnowledgeBaseRead]
    next_cursor: int | None = None


class KnowledgeBasePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    tags: list[str] | None = None


class KbSettingsRead(BaseModel):
    """Current per-KB provider settings (runtime state)."""

    id: int
    embedder_id: str | None = None
    vector_backend: str | None = None
    reranker_id: str | None = None
    chunker_id: str | None = None
    default_retrieval_policy_id: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)


class KbSettingsPatch(BaseModel):
    """Patch per-KB provider settings. Each value must be selectable from the
    deployment-declared + enabled set (enforced server-side)."""

    embedder_id: str | None = Field(default=None, max_length=128)
    vector_backend: str | None = Field(default=None, max_length=32)
    reranker_id: str | None = Field(default=None, max_length=128)
    chunker_id: str | None = Field(default=None, max_length=64)
    default_retrieval_policy_id: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=8)


class ProviderEntryRead(BaseModel):
    id: str
    enabled: bool
    endpoint: str | None = None
    has_credential: bool = False
    is_default: bool = False


class ProviderLayerRead(BaseModel):
    layer: str
    default_id: str | None = None
    items: list[ProviderEntryRead] = Field(default_factory=list)


class ProvidersConfigRead(BaseModel):
    """Deployment-declared provider universe for the RAG UI to select from.

    Includes ``chunkers`` (code-level set) alongside the deploy-config layers so
    the KB settings page can render every dropdown from one payload.
    """

    embedders: ProviderLayerRead
    vector_stores: ProviderLayerRead
    rerankers: ProviderLayerRead
    search_providers: ProviderLayerRead
    connectors: ProviderLayerRead
    chunkers: list[str] = Field(default_factory=list)


class DocumentRead(BaseModel):
    id: int
    knowledge_base_id: int
    filename: str
    status: str
    ingest_error: str | None = None
    created_at: object

    model_config = {"from_attributes": True}


class DocumentUploadResultRead(BaseModel):
    """``document_id`` is set when a row was persisted; omitted when the file was rejected (e.g. too large)."""

    document_id: int | None = None
    status: str
    filename: str
    ingest_error: str | None = None


class DocumentsUploadResponseRead(BaseModel):
    results: list[DocumentUploadResultRead]


ConnectorKind = Literal["files", "github", "gitlab", "confluence", "s3"]


class KnowledgeBaseConnectorCreate(BaseModel):
    kind: ConnectorKind
    label: str = Field(default="", max_length=255)
    settings: dict = Field(default_factory=dict)


class KnowledgeBaseConnectorPatch(BaseModel):
    label: str | None = Field(default=None, max_length=255)
    settings: dict | None = None
    enabled: bool | None = None


class KnowledgeBaseConnectorRead(BaseModel):
    id: int
    knowledge_base_id: int
    kind: str
    label: str
    settings: dict
    enabled: bool
    created_at: object

    model_config = {"from_attributes": True}


class ConnectorSyncJobRead(BaseModel):
    id: int
    knowledge_base_id: int
    connector_id: int
    job_type: str
    status: str
    error_message: str | None
    meta: dict
    created_at: object
    started_at: object | None
    finished_at: object | None

    model_config = {"from_attributes": True}


class PermissionTestRequest(BaseModel):
    """Probe what a given user can retrieve from this KB.

    ``user_id`` is the internal ``users.id`` whose visibility we want to
    inspect. ``group_ids`` is an optional override — when omitted, the
    user's group memberships are resolved (no SCIM; group_ids will be empty unless overridden).
    """

    user_id: int
    group_ids: list[str] | None = None
    sample_limit: int = Field(default=20, ge=0, le=200)


class PermissionTestDocSample(BaseModel):
    document_id: str
    title: str
    source_uri: str


class ScopedKbKeyCreate(BaseModel):
    name: str = Field(default="", max_length=128)


class ScopedKbKeyOut(BaseModel):
    """KB-scoped API key — public shape (no plaintext)."""

    id: _uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class ScopedKbKeyCreated(ScopedKbKeyOut):
    """Returned once on mint. Carries plaintext."""

    plaintext: str


class KbCloneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    include_documents: bool = False


class PlaygroundSaveAsEvalRequest(BaseModel):
    test_set_id: _uuid.UUID


class PermissionTestResponse(BaseModel):
    """Result of a permission probe.

    - ``visible_document_count`` — total docs the user could retrieve.
    - ``sample`` — first N docs (for the admin UI to render).
    - ``resolved_group_ids`` — the groups used in the probe (either
      provided in the request or loaded from SCIM membership).
    """

    user_id: int
    kb_id: int
    visible_document_count: int
    sample: list[PermissionTestDocSample]
    resolved_group_ids: list[str]
