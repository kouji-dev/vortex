# tests/chat/streaming/test_cancellation.py
import uuid

import pytest

from ai_portal.chat.streaming.cancellation import (
    CancelRegistry,
    CancelToken,
    cancel_turn,
    register_turn,
    release_turn,
)


def test_register_and_cancel():
    CancelRegistry.clear()
    turn_id = uuid.uuid4()
    token = CancelRegistry.register(turn_id)
    assert isinstance(token, CancelToken)
    assert not token.cancelled

    result = CancelRegistry.cancel(turn_id)
    assert result is True
    assert token.cancelled


def test_cancel_unknown_turn():
    CancelRegistry.clear()
    result = CancelRegistry.cancel(uuid.uuid4())
    assert result is False


def test_unregister_removes_from_registry():
    CancelRegistry.clear()
    turn_id = uuid.uuid4()
    CancelRegistry.register(turn_id)
    CancelRegistry.unregister(turn_id)

    # Cancelling an unregistered turn returns False
    result = CancelRegistry.cancel(turn_id)
    assert result is False


def test_token_cancel_is_idempotent():
    turn_id = uuid.uuid4()
    token = CancelToken(turn_id)
    token.cancel()
    token.cancel()  # Should not raise
    assert token.cancelled


# ---------------------------------------------------------------------------
# Module-level alias tests
# ---------------------------------------------------------------------------


def test_register_turn_returns_cancel_token():
    CancelRegistry.clear()
    turn_id = uuid.uuid4()
    token = register_turn(turn_id)
    assert isinstance(token, CancelToken)
    assert not token.cancelled


def test_release_turn_removes_registration():
    CancelRegistry.clear()
    turn_id = uuid.uuid4()
    register_turn(turn_id)
    release_turn(turn_id)
    # After release, cancelling returns False (not found)
    result = CancelRegistry.cancel(turn_id)
    assert result is False


@pytest.mark.asyncio
async def test_cancel_turn_trips_token():
    CancelRegistry.clear()
    turn_id = uuid.uuid4()
    token = register_turn(turn_id)
    assert not token.cancelled

    result = await cancel_turn(turn_id=turn_id)
    assert result is True
    assert token.cancelled


@pytest.mark.asyncio
async def test_cancel_turn_unknown_returns_false():
    CancelRegistry.clear()
    result = await cancel_turn(turn_id=uuid.uuid4())
    assert result is False
