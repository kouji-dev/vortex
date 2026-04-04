from ai_portal.models.org import Org


def test_org_model_has_expected_columns():
    cols = {c.name for c in Org.__table__.columns}
    assert "id" in cols
    assert "slug" in cols
    assert "name" in cols
    assert "instance_mode" in cols
    assert "archived_at" in cols
    assert "created_at" in cols
