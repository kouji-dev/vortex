import uuid
from unittest.mock import MagicMock, patch

import pytest

from ai_portal.auth.manager import UserManager, RegistrationError, AuthenticationError


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def manager(db):
    return UserManager(db=db, secret="testsecret")


def test_register_raises_on_duplicate_email(manager, db):
    existing = MagicMock()
    db.scalars.return_value.first.return_value = existing
    with pytest.raises(RegistrationError, match="Email already registered"):
        manager.register(email="exists@example.com", password="pass1234")


def test_authenticate_raises_on_bad_password(manager, db):
    from ai_portal.auth.password import hash_password
    user_mock = MagicMock()
    user_mock.hashed_password = hash_password("correctpass")
    user_mock.is_active = True
    db.scalars.return_value.first.return_value = user_mock
    with pytest.raises(AuthenticationError):
        manager.authenticate(email="x@x.com", password="wrongpass")


def test_authenticate_raises_when_user_not_found(manager, db):
    db.scalars.return_value.first.return_value = None
    with pytest.raises(AuthenticationError):
        manager.authenticate(email="x@x.com", password="anypass")
