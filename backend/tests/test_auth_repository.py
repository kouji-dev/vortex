"""Tests for auth/repository.py — DB query functions."""
import uuid

import pytest
from sqlalchemy.orm import Session

from ai_portal.core.db.session import SessionLocal
from ai_portal.auth.repository import get_user_by_uuid, get_user_by_email
from tests.conftest import requires_postgres


@requires_postgres
def test_get_user_by_uuid_missing():
    """Should return None for unknown UUID."""
    db = SessionLocal()
    try:
        result = get_user_by_uuid(db, uuid.uuid4())
        assert result is None
    finally:
        db.close()


@requires_postgres
def test_get_user_by_email_missing():
    """Should return None for unknown email."""
    db = SessionLocal()
    try:
        result = get_user_by_email(db, "nobody@example.invalid")
        assert result is None
    finally:
        db.close()
