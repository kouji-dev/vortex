from __future__ import annotations
import jwt
from jwt import PyJWKClient
from ai_portal.auth.idp.protocol import UserClaims

_clients: dict[str, PyJWKClient] = {}

def _client(uri: str) -> PyJWKClient:
    c = _clients.get(uri)
    if c is None:
        c = PyJWKClient(uri, cache_keys=True); _clients[uri] = c
    return c

def verify_id_token(token: str, *, jwks_uri: str, issuer: str, audience: str, leeway: int = 30) -> dict:
    key = _client(jwks_uri).get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=["RS256"], audience=audience, issuer=issuer,
                      leeway=leeway, options={"require": ["exp", "iat", "sub"]})

def make_claims(payload: dict) -> UserClaims:
    sub, email = payload.get("sub"), payload.get("email")
    if not sub or not email:
        raise jwt.InvalidTokenError("token missing 'sub' or 'email'")
    g = payload.get("groups") or ()
    groups = tuple(g) if isinstance(g, (list, tuple)) else ()
    return UserClaims(subject=str(sub), email=str(email), name=payload.get("name"), groups=groups, raw=payload)
