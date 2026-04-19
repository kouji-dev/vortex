"""Admin retention policy API + GDPR purge endpoint."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.core.db.rls import bypass_rls
from ai_portal.retention.model import RetentionPolicy
from ai_portal.retention.schemas import RetentionPolicyResponse, RetentionPolicyUpdate

router = APIRouter(prefix="/api/admin/retention", tags=["retention"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, ("admin", "owner"))
    return user


@router.get("/policy", response_model=RetentionPolicyResponse)
def get_policy(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> RetentionPolicyResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    with bypass_rls(db):
        policy = db.scalars(
            select(RetentionPolicy).where(RetentionPolicy.org_id == user.org_id)
        ).first()

    if policy is None:
        return RetentionPolicyResponse(
            id=0,
            org_id=user.org_id,
            conversation_retention_days=None,
            audit_retention_days=2555,
            usage_retention_days=2555,
            upload_retention_days=None,
            legal_hold=False,
            updated_at=datetime.now(UTC),
        )
    return RetentionPolicyResponse.model_validate(policy)


@router.put("/policy", response_model=RetentionPolicyResponse)
def update_policy(
    body: RetentionPolicyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> RetentionPolicyResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    with bypass_rls(db):
        policy = db.scalars(
            select(RetentionPolicy).where(RetentionPolicy.org_id == user.org_id)
        ).first()

        if policy is None:
            policy = RetentionPolicy(org_id=user.org_id)
            db.add(policy)

        policy.conversation_retention_days = body.conversation_retention_days
        policy.audit_retention_days = body.audit_retention_days
        policy.usage_retention_days = body.usage_retention_days
        policy.upload_retention_days = body.upload_retention_days
        policy.legal_hold = body.legal_hold
        policy.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(policy)

    try:
        from ai_portal.audit.service import log_event  # noqa: PLC0415
        log_event(
            org_id=user.org_id,
            actor_user_id=user.id,
            event_type="retention.policy.updated",
            resource_type="policy",
            resource_id=str(policy.id),
            action="update",
            metadata={"legal_hold": policy.legal_hold, "conversation_retention_days": policy.conversation_retention_days},
        )
    except ImportError:
        pass

    return RetentionPolicyResponse.model_validate(policy)


@router.delete("/users/{target_user_id}/data", status_code=204)
def purge_user_data(
    target_user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> None:
    """GDPR 'right to be forgotten' — delete all data for a user in this org.

    Cascades: conversations (+ messages, uploads on disk), memories, usage rows.
    Does NOT delete the user account itself — caller may do that separately.
    """
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    from ai_portal.chat.model import ChatConversation, ChatUpload  # noqa: PLC0415
    from ai_portal.memory.model import UserMemory  # noqa: PLC0415
    from ai_portal.usage.model import MessageUsage  # noqa: PLC0415
    from ai_portal.retention.sweeper import _delete_upload_file  # noqa: PLC0415

    with bypass_rls(db):
        # Verify target user belongs to this org.
        from ai_portal.auth.model import User as UserModel  # noqa: PLC0415
        target = db.get(UserModel, target_user_id)
        if target is None or target.org_id != user.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found in this org")

        # Uploads (disk + DB).
        uploads = db.scalars(
            select(ChatUpload).where(
                ChatUpload.org_id == user.org_id,
                ChatUpload.user_id == target_user_id,
                ChatUpload.legal_hold.is_(False),
            )
        ).all()
        for upload in uploads:
            _delete_upload_file(upload.stored_path)
            db.delete(upload)
        db.commit()

        # Conversations (cascades messages).
        convs = db.scalars(
            select(ChatConversation).where(
                ChatConversation.org_id == user.org_id,
                ChatConversation.user_id == target_user_id,
            )
        ).all()
        for conv in convs:
            db.delete(conv)
        db.commit()

        # Memories.
        memories = db.scalars(
            select(UserMemory).where(UserMemory.user_id == target_user_id)
        ).all()
        for m in memories:
            db.delete(m)

        # Usage rows — anonymize (set user_id to NULL) rather than delete to
        # preserve org-level spend history.
        db.execute(
            MessageUsage.__table__.update()
            .where(
                MessageUsage.org_id == user.org_id,
                MessageUsage.user_id == target_user_id,
            )
            .values(user_id=None)
        )
        db.commit()

    try:
        from ai_portal.audit.service import log_event  # noqa: PLC0415
        log_event(
            org_id=user.org_id,
            actor_user_id=user.id,
            event_type="gdpr.user_data_purged",
            resource_type="conversation",
            resource_id=str(target_user_id),
            action="delete",
            metadata={"target_user_id": target_user_id},
        )
    except ImportError:
        pass
