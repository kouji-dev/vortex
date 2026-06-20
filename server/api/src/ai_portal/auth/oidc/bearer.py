from __future__ import annotations
import jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from ai_portal.auth.oidc.jwks import verify_id_token, make_claims
from ai_portal.auth.oidc.role_map import map_groups_to_role
from ai_portal.auth.oidc.provisioning import jit_provision
from ai_portal.auth.model import User

def authenticate_oidc_bearer(db: Session, token: str, settings) -> tuple[User, str]:
    try:
        payload = verify_id_token(token, jwks_uri=settings.oidc_jwks_uri,
                                  issuer=settings.oidc_issuer, audience=settings.oidc_client_id)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid IdP token") from e
    claims = make_claims(payload)
    role = map_groups_to_role(claims.groups, settings.oidc_group_role_map or {})
    user = jit_provision(db, claims=claims, org_id=settings.oidc_default_org_id, role=role)
    return user, role
