from __future__ import annotations

import uuid as _uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.core.config import get_settings
from ai_portal.auth.model import User
from ai_portal.knowledge_base.model import CONNECTOR_KINDS
from ai_portal.knowledge_base.workers.connector_jobs import run_connector_sync_job
from ai_portal.knowledge_base import repository as repo
from ai_portal.knowledge_base import service as svc
from ai_portal.knowledge_base import ingest_service as ingest_svc
from ai_portal.knowledge_base.schemas import (
    ConnectorSyncJobRead,
    DocumentRead,
    DocumentsUploadResponseRead,
    KbCloneRequest,
    KnowledgeBaseConnectorCreate,
    KnowledgeBaseConnectorPatch,
    KnowledgeBaseConnectorRead,
    KnowledgeBaseCreate,
    KnowledgeBasePage,
    KnowledgeBasePatch,
    KnowledgeBaseRead,
    PermissionTestDocSample,
    PermissionTestRequest,
    PermissionTestResponse,
    ScopedKbKeyCreate,
    ScopedKbKeyCreated,
    ScopedKbKeyOut,
)
from ai_portal.knowledge_base import management as mgmt
from ai_portal.knowledge_base import scoped_keys as scoped
from ai_portal.api_keys.service import ApiKeyNotFound, ApiKeyService
from ai_portal.rag.acl.permission_test import run_permission_test

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


@router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    body: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> KnowledgeBaseRead:
    kb = repo.create_kb(
        db,
        name=body.name.strip(),
        description=(body.description or "").strip(),
        owner_user_id=user.id,
        org_id=org_id,
    )
    rows = svc.build_kb_rows(db, [kb])
    return rows[0]


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[KnowledgeBaseRead]:
    kbs = repo.list_kbs_by_user(db, user.id, org_id)
    return svc.build_kb_rows(db, kbs)


@router.get("/page", response_model=KnowledgeBasePage)
def list_knowledge_bases_page(
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> KnowledgeBasePage:
    rows = repo.list_kbs_by_user_page(db, user.id, org_id, limit, cursor)
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    items = svc.build_kb_rows(db, page_rows)
    next_cursor = page_rows[-1].id if has_more and page_rows else None
    return KnowledgeBasePage(items=items, next_cursor=next_cursor)


@router.get(
    "/{knowledge_base_id}/connector-jobs",
    response_model=list[ConnectorSyncJobRead],
)
def list_connector_jobs(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConnectorSyncJobRead]:
    svc.get_owned_kb(db, user, knowledge_base_id)
    return repo.list_connector_jobs(db, knowledge_base_id, limit)


@router.get(
    "/{knowledge_base_id}/connectors",
    response_model=list[KnowledgeBaseConnectorRead],
)
def list_connectors(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[KnowledgeBaseConnectorRead]:
    svc.get_owned_kb(db, user, knowledge_base_id)
    return repo.list_connectors_for_kb(db, knowledge_base_id)


@router.post(
    "/{knowledge_base_id}/connectors",
    response_model=KnowledgeBaseConnectorRead,
    status_code=status.HTTP_201_CREATED,
)
def create_connector(
    knowledge_base_id: int,
    body: KnowledgeBaseConnectorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> KnowledgeBaseConnectorRead:
    svc.get_owned_kb(db, user, knowledge_base_id)
    if body.kind not in CONNECTOR_KINDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid connector kind",
        )
    return repo.create_connector(
        db,
        kb_id=knowledge_base_id,
        kind=body.kind,
        label=(body.label or "").strip(),
        settings=body.settings or {},
    )


@router.patch(
    "/{knowledge_base_id}/connectors/{connector_id}",
    response_model=KnowledgeBaseConnectorRead,
)
def patch_connector(
    knowledge_base_id: int,
    connector_id: int,
    body: KnowledgeBaseConnectorPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> KnowledgeBaseConnectorRead:
    c = svc.get_owned_connector(db, user, knowledge_base_id, connector_id)
    return repo.update_connector(
        db, c,
        label=body.label.strip() if body.label is not None else None,
        settings=body.settings,
        enabled=body.enabled,
    )


@router.delete(
    "/{knowledge_base_id}/connectors/{connector_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_connector(
    knowledge_base_id: int,
    connector_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> None:
    c = svc.get_owned_connector(db, user, knowledge_base_id, connector_id)
    repo.delete_connector(db, c)


@router.post(
    "/{knowledge_base_id}/connectors/{connector_id}/sync",
    response_model=ConnectorSyncJobRead,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_connector_sync(
    knowledge_base_id: int,
    connector_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ConnectorSyncJobRead:
    c = svc.get_owned_connector(db, user, knowledge_base_id, connector_id)
    if not c.enabled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Connector is disabled",
        )
    job = repo.create_connector_sync_job(db, knowledge_base_id, connector_id)
    background_tasks.add_task(run_connector_sync_job, job.id)
    return job


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def get_knowledge_base(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> KnowledgeBaseRead:
    kb = svc.get_owned_kb(db, user, knowledge_base_id)
    rows = svc.build_kb_rows(db, [kb])
    return rows[0]


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def patch_knowledge_base(
    knowledge_base_id: int,
    body: KnowledgeBasePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> KnowledgeBaseRead:
    kb = svc.get_owned_kb(db, user, knowledge_base_id)
    kb = repo.update_kb(
        db, kb,
        name=body.name.strip() if body.name is not None else None,
        description=body.description.strip() if body.description is not None else None,
    )
    rows = svc.build_kb_rows(db, [kb])
    return rows[0]


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentRead])
def list_documents(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[DocumentRead]:
    svc.get_owned_kb(db, user, knowledge_base_id)
    return repo.list_documents_for_kb(db, knowledge_base_id)


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    knowledge_base_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> None:
    svc.get_owned_kb(db, user, knowledge_base_id)
    doc = repo.get_document_by_id(db, document_id)
    if doc is None or doc.knowledge_base_id != knowledge_base_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    repo.delete_document(db, doc)


@router.post(
    "/{knowledge_base_id}/documents",
    status_code=status.HTTP_200_OK,
    response_model=DocumentsUploadResponseRead,
)
async def upload_document(
    knowledge_base_id: int,
    file: list[UploadFile] = File(
        ...,
        description="One or more files (repeat the `file` field for each part).",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> DocumentsUploadResponseRead:
    """Persist uploads and queue ingest. Response returns immediately with ``pending``; worker sets ``ingesting`` then ``ready``/``failed``."""
    kb = svc.get_owned_kb(db, user, knowledge_base_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one file is required.",
        )
    settings = get_settings()
    results = []
    for part in file:
        results.append(
            await ingest_svc.store_and_queue_kb_upload(kb, part, db, settings, background_tasks)
        )
    return DocumentsUploadResponseRead(results=results)


@router.post(
    "/{knowledge_base_id}/permission-test",
    response_model=PermissionTestResponse,
)
def permission_test(
    knowledge_base_id: int,
    body: PermissionTestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> PermissionTestResponse:
    """Probe which documents in the KB a given user could retrieve."""
    svc.get_owned_kb(db, user, knowledge_base_id)
    outcome = run_permission_test(
        db,
        kb_id=knowledge_base_id,
        user_id=body.user_id,
        group_ids_override=body.group_ids,
        sample_limit=body.sample_limit,
    )
    return PermissionTestResponse(
        user_id=outcome.user_id,
        kb_id=outcome.kb_id,
        visible_document_count=outcome.visible_document_count,
        sample=[
            PermissionTestDocSample(
                document_id=str(s.document_id),
                title=s.title,
                source_uri=s.source_uri,
            )
            for s in outcome.sample
        ],
        resolved_group_ids=outcome.resolved_group_ids,
    )


@router.get(
    "/{knowledge_base_id}/api-keys",
    response_model=list[ScopedKbKeyOut],
)
def list_scoped_keys(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[ScopedKbKeyOut]:
    """List active KB-scoped API keys."""
    svc.get_owned_kb(db, user, knowledge_base_id)
    keys = scoped.list_scoped_kb_keys(db, org_id=org_id, kb_id=knowledge_base_id)
    return [
        ScopedKbKeyOut(
            id=k.id,
            name=k.name,
            prefix=k.prefix,
            scopes=list(k.scopes_json or []),
            created_at=k.created_at,
            last_used_at=k.last_used_at,
            revoked_at=k.revoked_at,
        )
        for k in keys
    ]


@router.post(
    "/{knowledge_base_id}/api-keys",
    response_model=ScopedKbKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
def mint_scoped_key(
    knowledge_base_id: int,
    body: ScopedKbKeyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ScopedKbKeyCreated:
    """Mint a read-only API key bound to this KB. Plaintext shown once."""
    svc.get_owned_kb(db, user, knowledge_base_id)
    minted = scoped.mint_scoped_kb_key(
        db,
        org_id=org_id,
        kb_id=knowledge_base_id,
        name=body.name.strip(),
        actor_user_id=user.id,
    )
    key = ApiKeyService(db).get(org_id=org_id, key_id=minted.key_id)
    return ScopedKbKeyCreated(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        scopes=list(key.scopes_json or []),
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        plaintext=minted.plaintext,
    )


@router.delete(
    "/{knowledge_base_id}/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_scoped_key(
    knowledge_base_id: int,
    key_id: _uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> None:
    svc.get_owned_kb(db, user, knowledge_base_id)
    row = scoped.get_scoped_kb_key(
        db, org_id=org_id, kb_id=knowledge_base_id, key_id=key_id
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Scoped key not found")
    try:
        ApiKeyService(db).revoke(org_id=org_id, key_id=key_id)
    except ApiKeyNotFound as e:  # pragma: no cover
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Scoped key not found") from e


@router.post(
    "/{knowledge_base_id}/clone",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
def clone_kb(
    knowledge_base_id: int,
    body: KbCloneRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> KnowledgeBaseRead:
    """Clone KB settings + connectors. Documents copied only if include_documents=True."""
    src = svc.get_owned_kb(db, user, knowledge_base_id)
    dst = mgmt.clone_kb(db, src, new_name=body.name.strip())
    if body.include_documents:
        mgmt.copy_documents(db, src_kb_id=src.id, dst_kb_id=dst.id)
    rows = svc.build_kb_rows(db, [dst])
    return rows[0]


@router.get("/{kb_id}/documents/{doc_id}/progress")
def get_document_progress(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> dict:
    """Return ingest progress for a document."""
    doc = repo.get_document_in_kb(db, doc_id, kb_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": doc.id,
        "status": doc.status,
        "chunks_done": doc.chunks_done,
        "chunks_total": doc.chunks_total,
        "ingest_error": doc.ingest_error,
    }
