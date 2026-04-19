import uuid
from unittest.mock import MagicMock, patch

from ai_portal.core.db.tenant import TenantRepository


class FakeModel:
    __tablename__ = "fake"
    id = None
    org_id = None


def test_get_returns_none_when_not_found():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    repo = TenantRepository(db=db, model=FakeModel)
    org_id = uuid.uuid4()
    with patch("ai_portal.core.db.tenant.select") as mock_select:
        mock_select.return_value = MagicMock()
        result = repo.get(id=1, org_id=org_id)
        assert result is None


def test_get_calls_db():
    db = MagicMock()
    org_id = uuid.uuid4()
    db.scalars.return_value.first.return_value = MagicMock()
    repo = TenantRepository(db=db, model=FakeModel)
    with patch("ai_portal.core.db.tenant.select") as mock_select:
        mock_select.return_value = MagicMock()
        repo.get(id=1, org_id=org_id)
        assert db.scalars.called
