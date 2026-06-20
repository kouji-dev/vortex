import json, time, jwt, pytest, respx
from ai_portal.auth.oidc.jwks import verify_id_token, make_claims

def _jwks(key, kid="k1"):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())); jwk["kid"] = kid
    return {"keys": [jwk]}

def _claims(**over):
    now = int(time.time())
    base = {"sub":"u1","email":"a@b.c","iss":"https://idp.test","aud":"vortex-app","iat":now,"exp":now+3600}
    base.update(over)
    return base

def test_verifies_valid_token(rsa_key, mock_jwks_client):
    tok = jwt.encode(_claims(), rsa_key, algorithm="RS256", headers={"kid":"k1"})
    assert verify_id_token(tok, jwks_uri="https://idp.test/jwks", issuer="https://idp.test", audience="vortex-app")["sub"] == "u1"

def test_rejects_wrong_audience(rsa_key, mock_jwks_client):
    tok = jwt.encode(_claims(aud="other"), rsa_key, algorithm="RS256", headers={"kid":"k1"})
    with pytest.raises(jwt.InvalidAudienceError):
        verify_id_token(tok, jwks_uri="https://idp.test/jwks", issuer="https://idp.test", audience="vortex-app")

def test_rejects_wrong_issuer(rsa_key, mock_jwks_client):
    tok = jwt.encode(_claims(iss="https://evil.test"), rsa_key, algorithm="RS256", headers={"kid":"k1"})
    with pytest.raises(jwt.InvalidIssuerError):
        verify_id_token(tok, jwks_uri="https://idp.test/jwks", issuer="https://idp.test", audience="vortex-app")

def test_make_claims_groups():
    uc = make_claims({"sub":"u1","email":"a@b.c","groups":["Eng"]})
    assert uc.subject=="u1" and uc.groups==("Eng",)
