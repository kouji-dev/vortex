"""GitHub connection service.

Validates a PAT, discovers repos, and persists the integration +
repo list in ``git_integrations`` / ``git_repos``.

All HTTP is isolated in ``_github_get`` so tests can monkeypatch it.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.core.crypto.envelope import decrypt_json, encrypt_json
from ai_portal.workers.model import GitIntegration, GitRepo

_GH_BASE = "https://api.github.com"


class InvalidGitToken(Exception):
    """Raised when the GitHub token is rejected by the API."""


# ---------------------------------------------------------------------------
# HTTP helper — isolated so tests can stub it
# ---------------------------------------------------------------------------


async def _github_get(token: str, path: str) -> httpx.Response:
    """GET ``{_GH_BASE}{path}`` with a Bearer token. Returns the raw response."""
    url = f"{_GH_BASE}{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    return resp


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def connect_github(
    db: Session,
    *,
    owner_user_id: uuid.UUID | None,
    org_id: uuid.UUID | None,
    token: str,
) -> GitIntegration:
    """Validate token, upsert integration + repos, return the integration row."""
    if bool(owner_user_id) == bool(org_id):
        raise ValueError("Exactly one of owner_user_id / org_id must be set")

    # 1. Validate token and get login.
    resp = await _github_get(token, "/user")
    if resp.status_code != 200:
        raise InvalidGitToken(
            f"GitHub token rejected (HTTP {resp.status_code}): {resp.text}"
        )
    account_login: str = resp.json()["login"]

    # 2. Upsert GitIntegration — find existing by owner.
    stmt = select(GitIntegration).where(GitIntegration.kind == "github")
    if owner_user_id:
        stmt = stmt.where(GitIntegration.user_id == owner_user_id)
    else:
        stmt = stmt.where(GitIntegration.org_id == org_id)

    integration: GitIntegration | None = db.scalars(stmt).first()

    if integration is None:
        integration = GitIntegration(
            kind="github",
            auth_type="token",
            account_login=account_login,
            config_encrypted=encrypt_json({"token": token}),
            enabled=True,
            user_id=owner_user_id,
            org_id=org_id,
        )
        db.add(integration)
        db.flush()  # get the id
    else:
        integration.account_login = account_login
        integration.config_encrypted = encrypt_json({"token": token})
        integration.auth_type = "token"
        integration.enabled = True
        db.flush()

    # 3. List repos and upsert GitRepo rows.
    repos_resp = await _github_get(token, "/user/repos?per_page=100&sort=updated")
    repos_data: list[dict[str, Any]] = repos_resp.json() if repos_resp.status_code == 200 else []

    for repo in repos_data:
        full_name: str = repo["full_name"]
        default_branch: str = repo.get("default_branch") or "main"

        existing_repo = db.scalars(
            select(GitRepo).where(
                GitRepo.integration_id == integration.id,
                GitRepo.full_name == full_name,
            )
        ).first()

        if existing_repo is None:
            db.add(
                GitRepo(
                    integration_id=integration.id,
                    full_name=full_name,
                    default_branch=default_branch,
                    enabled=False,
                )
            )
        else:
            existing_repo.default_branch = default_branch

    db.commit()
    db.refresh(integration)
    return integration


def list_integrations(
    db: Session,
    *,
    owner_user_id: uuid.UUID | None,
    org_id: uuid.UUID | None,
) -> list[GitIntegration]:
    """Return integrations owned by this user and/or org."""
    clauses = []
    if owner_user_id:
        from sqlalchemy import or_

        clauses.append(GitIntegration.user_id == owner_user_id)
    if org_id:
        from sqlalchemy import or_

        clauses.append(GitIntegration.org_id == org_id)
    if not clauses:
        return []
    from sqlalchemy import or_

    return list(db.scalars(select(GitIntegration).where(or_(*clauses))).all())


def list_repos(db: Session, integration_id: uuid.UUID) -> list[GitRepo]:
    """Return all repos for the given integration."""
    return list(
        db.scalars(
            select(GitRepo).where(GitRepo.integration_id == integration_id)
        ).all()
    )


def set_enabled_repos(
    db: Session,
    integration_id: uuid.UUID,
    enabled_full_names: set[str],
) -> list[GitRepo]:
    """Set enabled=True for repos in *enabled_full_names*, False for the rest."""
    repos = list_repos(db, integration_id)
    for repo in repos:
        repo.enabled = repo.full_name in enabled_full_names
    db.flush()
    return repos


def delete_integration(db: Session, integration_id: uuid.UUID) -> None:
    """Delete the integration (cascades to git_repos via FK)."""
    integration = db.get(GitIntegration, integration_id)
    if integration is not None:
        db.delete(integration)
        db.flush()


def decrypt_token(integration: GitIntegration) -> str:
    """Decrypt and return the raw token stored on the integration."""
    payload = decrypt_json(integration.config_encrypted)
    if not isinstance(payload, dict) or "token" not in payload:
        raise ValueError("integration config_encrypted does not contain a token")
    return payload["token"]
