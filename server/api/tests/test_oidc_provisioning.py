import uuid, pytest
from sqlalchemy import select
from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.model import User
from ai_portal.auth.oidc.provisioning import jit_provision
from tests.conftest import requires_postgres
pytestmark = requires_postgres

def test_creates_user_first_login(db_session, org):
    u = jit_provision(db_session, claims=UserClaims(subject="kc|1", email="new@acme.test", name="New"), org_id=org.id, role="member")
    assert u.id and u.org_id == org.id and u.role == "member" and u.is_active

def test_idempotent_updates_role(db_session, org):
    c = UserClaims(subject="kc|2", email="dup@acme.test", name="Dup")
    a = jit_provision(db_session, claims=c, org_id=org.id, role="member")
    b = jit_provision(db_session, claims=c, org_id=org.id, role="admin")
    assert a.id == b.id and b.role == "admin"
    assert len(db_session.scalars(select(User).where(User.email == "dup@acme.test")).all()) == 1
