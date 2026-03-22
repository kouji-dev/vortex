from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient


def issuer_v2(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/v2.0"


@lru_cache(maxsize=16)
def _jwks_client(tenant_id: str) -> PyJWKClient:
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return PyJWKClient(url)


def roles_from_claims(claims: dict[str, Any]) -> list[str]:
    raw = claims.get("roles")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return [str(raw)]


def decode_entra_access_token(
    token: str,
    *,
    tenant_id: str,
    audience: str,
    jwks_client: PyJWKClient | None = None,
) -> dict[str, Any]:
    """Validate an Entra access token (v2.0) and return claims."""
    client = jwks_client or _jwks_client(tenant_id)
    signing_key = client.get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer_v2(tenant_id),
        options={"require": ["exp", "iss", "aud"]},
    )
    tid = payload.get("tid")
    if tid != tenant_id:
        raise ValueError("Token tid does not match configured tenant")
    return payload
