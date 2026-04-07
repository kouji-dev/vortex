import uuid

import pytest

from ai_portal.auth.password import hash_password, verify_password
from ai_portal.auth.jwt import create_access_token, create_refresh_token, decode_token


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_access_token():
    user_uuid = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_access_token(
        user_uuid=user_uuid, org_id=org_id, role="member", secret="testsecret"
    )
    payload = decode_token(token, secret="testsecret")
    assert payload["sub"] == str(user_uuid)
    assert payload["org_id"] == str(org_id)
    assert payload["role"] == "member"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    user_uuid = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_refresh_token(
        user_uuid=user_uuid, org_id=org_id, role="admin", secret="testsecret"
    )
    payload = decode_token(token, secret="testsecret")
    assert payload["type"] == "refresh"


def test_decode_token_wrong_secret_raises():
    user_uuid = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_access_token(user_uuid=user_uuid, org_id=org_id, role="member", secret="good")
    with pytest.raises(Exception):
        decode_token(token, secret="bad")


def test_settings_deployment_mode_defaults_to_dev():
    import os
    # Save and clear env vars that might affect this test
    from ai_portal.config import Settings
    s = Settings()
    assert s.deployment_mode == "dev"


def test_settings_has_secret_key_field():
    from ai_portal.config import Settings
    s = Settings(SECRET_KEY="mysecret")
    assert s.secret_key == "mysecret"


def test_get_current_org_id_returns_uuid():
    from unittest.mock import MagicMock
    from ai_portal.auth.deps import get_current_org_id

    user = MagicMock()
    user.org_id = uuid.uuid4()
    result = get_current_org_id(user=user)
    assert result == user.org_id


def test_get_current_org_id_raises_when_no_org():
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    from ai_portal.auth.deps import get_current_org_id

    user = MagicMock()
    user.org_id = None
    with pytest.raises(HTTPException) as exc:
        get_current_org_id(user=user)
    assert exc.value.status_code == 403
