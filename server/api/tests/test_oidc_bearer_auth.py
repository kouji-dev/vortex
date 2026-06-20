import time, jwt
from ai_portal.auth.oidc.bearer import authenticate_oidc_bearer
from tests.conftest import requires_postgres
pytestmark = requires_postgres

class _S:
    oidc_issuer="https://idp.test"; oidc_jwks_uri="https://idp.test/jwks"
    oidc_client_id="vortex-app"; oidc_group_role_map={"IT-Admins":"admin"}

def test_valid_token_provisions_and_maps(db_session, org, rsa_key, mock_jwks_client):
    now = int(time.time())
    tok = jwt.encode({"sub":"kc|9","email":"alice@acme.test","groups":["IT-Admins"],
                      "iss":"https://idp.test","aud":"vortex-app","iat":now,"exp":now+3600},
                     rsa_key, algorithm="RS256", headers={"kid":"k1"})
    s = _S(); s.oidc_default_org_id = org.id
    user, role = authenticate_oidc_bearer(db_session, tok, s)
    assert user.email == "alice@acme.test" and role == "admin"
