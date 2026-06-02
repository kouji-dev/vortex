"""Tests for GitIntegration owner/auth fields and GitRepo model."""

from ai_portal.workers.model import GitIntegration, GitRepo


def test_git_integration_has_owner_and_auth_fields():
    cols = GitIntegration.__table__.c
    assert "user_id" in cols and cols.user_id.nullable is True
    assert "account_login" in cols
    assert "auth_type" in cols


def test_git_repo_model():
    cols = GitRepo.__table__.c
    for name in ("id", "integration_id", "full_name", "default_branch", "enabled", "created_at"):
        assert name in cols
    assert GitRepo.__tablename__ == "git_repos"
