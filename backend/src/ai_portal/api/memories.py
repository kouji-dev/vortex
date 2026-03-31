"""User profile memories CRUD API."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_current_user, get_db
from ai_portal.models.memory import UserMemory
from ai_portal.models.user import User

router = APIRouter(prefix="/api/users/me/memories", tags=["memories"])


class MemoryOut(BaseModel):
    id: int
    content: str
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateMemoryBody(BaseModel):
    content: str


class UpdateMemoryBody(BaseModel):
    content: str | None = None
    is_active: bool | None = None


@router.get("", response_model=list[MemoryOut])
def list_memories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[UserMemory]:
    return list(
        db.scalars(
            select(UserMemory)
            .where(UserMemory.user_id == user.id)
            .order_by(UserMemory.is_active.desc(), UserMemory.created_at.desc())
        ).all()
    )


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(
    body: CreateMemoryBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserMemory:
    mem = UserMemory(
        user_id=user.id,
        content=body.content,
        source="manual",
        is_active=True,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: int,
    body: UpdateMemoryBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserMemory:
    mem = db.get(UserMemory, memory_id)
    if mem is None or mem.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Memory not found")
    if body.content is not None:
        mem.content = body.content
    if body.is_active is not None:
        mem.is_active = body.is_active
    db.commit()
    db.refresh(mem)
    return mem


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    mem = db.get(UserMemory, memory_id)
    if mem is None or mem.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Memory not found")
    db.delete(mem)
    db.commit()
