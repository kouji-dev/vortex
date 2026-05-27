from ai_portal.auth.model import (
    EmailVerification,
    Org,
    OrgMember,
    PasswordReset,
    User,
    UserMfaFactor,
    UserSession,
)


def test_org_model_has_expected_columns():
    cols = {c.name for c in Org.__table__.columns}
    assert "id" in cols
    assert "slug" in cols
    assert "name" in cols
    assert "instance_mode" in cols
    assert "archived_at" in cols
    assert "created_at" in cols
    # control-plane additions
    assert "region" in cols
    assert "status" in cols


def test_user_model_has_auth_columns():
    cols = {c.name for c in User.__table__.columns}
    assert "uuid" in cols
    assert "org_id" in cols
    assert "role" in cols
    assert "is_active" in cols
    assert "is_verified" in cols
    assert "is_superuser" in cols
    # control-plane additions
    assert "name" in cols
    assert "locale" in cols
    assert "mfa_required" in cols
    assert "email_verified_at" in cols


def test_user_session_model_columns():
    cols = {c.name for c in UserSession.__table__.columns}
    assert {"id", "user_id", "token_hash", "expires_at", "revoked_at"} <= cols


def test_user_mfa_factor_model_columns():
    cols = {c.name for c in UserMfaFactor.__table__.columns}
    assert {"id", "user_id", "kind", "secret", "confirmed_at"} <= cols


def test_email_verification_columns():
    cols = {c.name for c in EmailVerification.__table__.columns}
    assert {"id", "user_id", "token_hash", "expires_at", "consumed_at"} <= cols


def test_password_reset_columns():
    cols = {c.name for c in PasswordReset.__table__.columns}
    assert {"id", "user_id", "token_hash", "expires_at", "consumed_at"} <= cols


def test_org_member_columns():
    cols = {c.name for c in OrgMember.__table__.columns}
    assert {"id", "org_id", "user_id", "role", "created_at", "removed_at"} <= cols


def test_org_member_unique_constraint():
    constraints = {
        c.name
        for c in OrgMember.__table__.constraints
        if c.name
    }
    assert "uq_org_members_org_user" in constraints
