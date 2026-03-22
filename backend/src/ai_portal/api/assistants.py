from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_current_user, get_db
from ai_portal.models import Assistant, AssistantAcl, User

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


def _visible_assistants_stmt(user: User):
    acl = select(AssistantAcl.assistant_id).where(AssistantAcl.user_id == user.id)
    return select(Assistant).where(
        or_(
            Assistant.owner_user_id == user.id,
            Assistant.visibility == "org",
            Assistant.id.in_(acl),
        )
    )


def _can_access_assistant(db: Session, user: User, assistant: Assistant) -> bool:
    if assistant.owner_user_id == user.id or assistant.visibility == "org":
        return True
    return (
        db.scalars(
            select(AssistantAcl).where(
                AssistantAcl.assistant_id == assistant.id,
                AssistantAcl.user_id == user.id,
            )
        ).first()
        is not None
    )


@router.get("", response_model=list[AssistantRead])
def list_assistants(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Assistant]:
    return list(db.scalars(_visible_assistants_stmt(user).order_by(Assistant.id)))


@router.post("", response_model=AssistantRead, status_code=status.HTTP_201_CREATED)
def create_assistant(
    body: AssistantCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Assistant:
    a = Assistant(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        owner_user_id=user.id,
        visibility=body.visibility,
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
) -> Assistant:
    a = db.get(Assistant, assistant_id)
    if a is None or not _can_access_assistant(db, user, a):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assistant not found")
    return a
