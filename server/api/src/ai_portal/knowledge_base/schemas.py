from __future__ import annotations

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
