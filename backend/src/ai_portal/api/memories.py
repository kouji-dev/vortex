"""User profile memories CRUD API."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import uuid as _uuid

from ai_portal.api.deps import get_current_org_id, get_current_user, get_db
from ai_portal.models.memory import UserMemory
from ai_portal.models.user import User

router = APIRouter(prefix="/api/users/me/memories", tags=["memories"])


class MemoryOut(BaseModel):
    id: int
    content: str
    source: str
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateMemoryBody(BaseModel):
    content: str


class UpdateMemoryBody(BaseModel):
    content: str | None = None
    is_active: bool | None = None


class MemoryPage(BaseModel):
    items: list[MemoryOut]
    next_cursor: int | None = None


@router.get("", response_model=list[MemoryOut])
def list_memories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[UserMemory]:
    return list(
        db.scalars(
            select(UserMemory)
            .where(UserMemory.user_id == user.id)
            .where(UserMemory.org_id == org_id)
            .order_by(UserMemory.is_active.desc(), UserMemory.created_at.desc())
        ).all()
    )


@router.get("/page", response_model=MemoryPage)
def list_memories_page(
    cursor: int | None = Query(default=None, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> MemoryPage:
    """Paginate manual memories by id; the single ``is_system`` row is always first on page 1."""
    system_row = db.scalars(
        select(UserMemory).where(
            UserMemory.user_id == user.id,
            UserMemory.org_id == org_id,
            UserMemory.is_system.is_(True),
        )
    ).first()

    if cursor is None:
        reserved = 1 if system_row is not None else 0
        nonsys_take = max(0, limit - reserved)
        stmt = (
            select(UserMemory)
            .where(
                UserMemory.user_id == user.id,
                UserMemory.org_id == org_id,
                UserMemory.is_system.is_(False),
            )
            .order_by(UserMemory.id.desc())
            .limit(nonsys_take + 1)
        )
        nonsys = list(db.scalars(stmt).all())
        has_more = len(nonsys) > nonsys_take
        nonsys = nonsys[:nonsys_take]
        items = ([system_row] if system_row else []) + nonsys
        next_cursor = nonsys[-1].id if has_more and nonsys else None
        return MemoryPage(items=items, next_cursor=next_cursor)

    stmt = (
        select(UserMemory)
        .where(
            UserMemory.user_id == user.id,
            UserMemory.org_id == org_id,
            UserMemory.is_system.is_(False),
            UserMemory.id < cursor,
        )
        .order_by(UserMemory.id.desc())
        .limit(limit + 1)
    )
    rows = list(db.scalars(stmt).all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None
    return MemoryPage(items=items, next_cursor=next_cursor)


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(
    body: CreateMemoryBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> UserMemory:
    mem = UserMemory(
        user_id=user.id,
        org_id=org_id,
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
    org_id: _uuid.UUID = Depends(get_current_org_id),
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
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> None:
    mem = db.get(UserMemory, memory_id)
    if mem is None or mem.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Memory not found")
    if mem.is_system:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The auto-maintained profile cannot be deleted; pause it instead.",
        )
    db.delete(mem)
    db.commit()
