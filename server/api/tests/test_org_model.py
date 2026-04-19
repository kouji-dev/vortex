from ai_portal.auth.model import Org, User


def test_org_model_has_expected_columns():
    cols = {c.name for c in Org.__table__.columns}
    assert "id" in cols
    assert "slug" in cols
    assert "name" in cols
    assert "instance_mode" in cols
    assert "archived_at" in cols
    assert "created_at" in cols


def test_user_model_has_auth_columns():
    cols = {c.name for c in User.__table__.columns}
    assert "uuid" in cols
    assert "org_id" in cols
    assert "role" in cols
    assert "is_active" in cols
    assert "is_verified" in cols
    assert "is_superuser" in cols
