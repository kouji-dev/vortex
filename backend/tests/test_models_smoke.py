from sqlalchemy import func, select

from ai_portal.db.session import SessionLocal
from ai_portal.models import User
from tests.conftest import requires_postgres


@requires_postgres
def test_dev_user_seeded():
    db = SessionLocal()
    try:
        n = db.scalar(select(func.count()).select_from(User))
        assert n is not None and n >= 1
    finally:
        db.close()
