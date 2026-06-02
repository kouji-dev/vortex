"""Pydantic schemas for git-integrations endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GitIntegrationConnect(BaseModel):
    kind: str = "github"
    scope: Literal["user", "org"]
    token: str = Field(min_length=1)


class GitRepoOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    full_name: str
    default_branch: str
    enabled: bool

    @classmethod
    def from_orm_row(cls, row) -> "GitRepoOut":
        return cls(
            id=str(row.id),
            full_name=row.full_name,
            default_branch=row.default_branch,
            enabled=row.enabled,
        )


class GitIntegrationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    kind: str
    account_login: str | None
    scope: str  # "user" if user_id else "org"
    auth_type: str
    enabled: bool
    repos: list[GitRepoOut]

    @classmethod
    def from_orm_row(cls, integration, repos) -> "GitIntegrationOut":
        return cls(
            id=str(integration.id),
            kind=integration.kind,
            account_login=integration.account_login,
            scope="user" if integration.user_id is not None else "org",
            auth_type=integration.auth_type,
            enabled=integration.enabled,
            repos=[GitRepoOut.from_orm_row(r) for r in repos],
        )


class ReposToggle(BaseModel):
    enabled_full_names: list[str]
