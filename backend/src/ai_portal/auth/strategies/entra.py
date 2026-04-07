from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient


def issuer_variants(tenant_id: str) -> list[str]:
    """Accept Entra access tokens whose `iss` is v2.0 or v1-style (sts.windows.net).

    MSAL often returns access tokens with ``ver`` 1.0 and issuer
    ``https://sts.windows.net/{tenant}/`` while ID tokens use login.microsoftonline v2.0.
    """
    tid = tenant_id.strip()
    if not tid:
        return []
    tid_lower = tid.lower()
    candidates = (
        f"https://login.microsoftonline.com/{tid}/v2.0",
        f"https://login.microsoftonline.com/{tid_lower}/v2.0",
        f"https://sts.windows.net/{tid}/",
        f"https://sts.windows.net/{tid_lower}/",
        f"https://sts.windows.net/{tid}",
        f"https://sts.windows.net/{tid_lower}",
    )
    seen: set[str] = set()
    out: list[str] = []
    for x in candidates:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


@lru_cache(maxsize=16)
def _jwks_client(tenant_id: str) -> PyJWKClient:
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return PyJWKClient(url)


def audience_variants(audience: str) -> list[str]:
    """Entra may issue `aud` as `api://{app-id}` or as the bare application (client) id."""
    raw = audience.strip()
    if not raw:
        return []
    out = [raw]
    if raw.startswith("api://"):
        bare = raw.removeprefix("api://").strip()
        if bare and bare not in out:
            out.append(bare)
    elif raw.count("-") == 4:
        api_form = f"api://{raw}"
        if api_form not in out:
            out.append(api_form)
    return out


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
    """Validate an Entra access token (v1 or v2 issuer) and return claims."""
    client = jwks_client or _jwks_client(tenant_id)
    signing_key = client.get_signing_key_from_jwt(token)
    auds = audience_variants(audience)
    if not auds:
        msg = "audience must be a non-empty ENTRA_API_AUDIENCE"
        raise ValueError(msg)
    issuers = issuer_variants(tenant_id)
    if not issuers:
        msg = "tenant_id must be non-empty for Entra issuer validation"
        raise ValueError(msg)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=auds,
        issuer=issuers,
        leeway=60,
        options={"require": ["exp", "iss", "aud"]},
    )
    tid = payload.get("tid")
    if not isinstance(tid, str) or tid.lower() != tenant_id.strip().lower():
        raise ValueError("Token tid does not match configured tenant")
    return payload
