import uuid as _uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.assistant.model import Assistant, AssistantAcl
from ai_portal.auth.model import User

router = APIRouter(prefix="/api/assistants", tags=["assistants"])


class AssistantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    system_prompt: str = ""
    visibility: Literal["private", "org"] = "private"


class AssistantRead(BaseModel):
    id: int
    name: str
    description: str
    system_prompt: str
    owner_user_id: int
    visibility: str

    model_config = {"from_attributes": True}


class AssistantPatch(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    system_prompt: str | None = None
    visibility: Literal["private", "org"] | None = None


def _visible_assistants_stmt(user: User, org_id: _uuid.UUID):
    acl = select(AssistantAcl.assistant_id).where(AssistantAcl.user_id == user.id)
    return select(Assistant).where(
        Assistant.org_id == org_id,
        or_(
            Assistant.owner_user_id == user.id,
            Assistant.visibility == "org",
            Assistant.id.in_(acl),
        ),
    )


def _can_access_assistant(
    assistant_id: int, user: User, org_id: _uuid.UUID, db: Session
) -> Assistant:
    stmt = _visible_assistants_stmt(user, org_id).where(Assistant.id == assistant_id)
    assistant = db.scalars(stmt).first()
    if assistant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assistant not found")
    return assistant


@router.get("", response_model=list[AssistantRead])
def list_assistants(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[Assistant]:
    return list(db.scalars(_visible_assistants_stmt(user, org_id).order_by(Assistant.id)))


@router.post("", response_model=AssistantRead, status_code=status.HTTP_201_CREATED)
def create_assistant(
    body: AssistantCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> Assistant:
    a = Assistant(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        owner_user_id=user.id,
        visibility=body.visibility,
        org_id=org_id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.get("/{assistant_id}", response_model=AssistantRead)
def get_assistant(
    assistant_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> Assistant:
    return _can_access_assistant(assistant_id, user, org_id, db)


@router.patch("/{assistant_id}", response_model=AssistantRead)
def patch_assistant(
    assistant_id: int,
    body: AssistantPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> Assistant:
    a = _can_access_assistant(assistant_id, user, org_id, db)
    if a.owner_user_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only the assistant owner can edit",
        )
    if "name" in body.model_fields_set:
        if body.name is None or not body.name.strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="name cannot be empty",
            )
        a.name = body.name.strip()
    if "description" in body.model_fields_set:
        a.description = "" if body.description is None else body.description
    if "system_prompt" in body.model_fields_set:
        a.system_prompt = "" if body.system_prompt is None else body.system_prompt
    if "visibility" in body.model_fields_set and body.visibility is not None:
        a.visibility = body.visibility
    db.commit()
    db.refresh(a)
    return a
