import json, jwt, pytest, respx
from cryptography.hazmat.primitives.asymmetric import rsa
from ai_portal.auth.oidc.jwks import verify_id_token, make_claims

@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)

def _jwks(key, kid="k1"):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())); jwk["kid"] = kid
    return {"keys": [jwk]}

@respx.mock
def test_verifies_valid_token(rsa_key):
    respx.get("https://idp.test/jwks").respond(json=_jwks(rsa_key))
    tok = jwt.encode({"sub":"u1","email":"a@b.c","iss":"https://idp.test","aud":"vortex-app"}, rsa_key, algorithm="RS256", headers={"kid":"k1"})
    assert verify_id_token(tok, jwks_uri="https://idp.test/jwks", issuer="https://idp.test", audience="vortex-app")["sub"] == "u1"

@respx.mock
def test_rejects_wrong_audience(rsa_key):
    respx.get("https://idp.test/jwks").respond(json=_jwks(rsa_key))
    tok = jwt.encode({"sub":"u1","email":"a@b.c","iss":"https://idp.test","aud":"other"}, rsa_key, algorithm="RS256", headers={"kid":"k1"})
    with pytest.raises(jwt.InvalidAudienceError):
        verify_id_token(tok, jwks_uri="https://idp.test/jwks", issuer="https://idp.test", audience="vortex-app")

def test_make_claims_groups():
    uc = make_claims({"sub":"u1","email":"a@b.c","groups":["Eng"]})
    assert uc.subject=="u1" and uc.groups==("Eng",)
