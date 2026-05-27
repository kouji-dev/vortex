"""HMAC-SHA256 webhook signing — wire format ``v1=<hex>``."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from ai_portal.webhooks.signer import SIG_PREFIX, sign_payload, verify_signature


def test_sign_payload_prefix_and_hex_length() -> None:
    sig = sign_payload(b'{"event":"ping"}', b"super-secret")
    assert sig.startswith(SIG_PREFIX)
    hex_part = sig[len(SIG_PREFIX) :]
    assert len(hex_part) == 64  # SHA-256 hex digest length
    int(hex_part, 16)  # raises if non-hex


def test_sign_payload_is_reproducible() -> None:
    payload = b'{"a":1,"b":2}'
    secret = b"shh"
    assert sign_payload(payload, secret) == sign_payload(payload, secret)


def test_sign_payload_matches_raw_hmac() -> None:
    payload = b"hello"
    secret = b"k"
    expected = "v1=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
    assert sign_payload(payload, secret) == expected


def test_sign_payload_changes_with_payload() -> None:
    secret = b"k"
    assert sign_payload(b"a", secret) != sign_payload(b"b", secret)


def test_sign_payload_changes_with_secret() -> None:
    payload = b"x"
    assert sign_payload(payload, b"k1") != sign_payload(payload, b"k2")


def test_verify_signature_round_trip() -> None:
    payload = b"hello world"
    secret = b"deadbeef"
    sig = sign_payload(payload, secret)
    assert verify_signature(payload, secret, sig) is True


def test_verify_signature_rejects_wrong_secret() -> None:
    sig = sign_payload(b"x", b"k1")
    assert verify_signature(b"x", b"k2", sig) is False


def test_verify_signature_rejects_tampered_payload() -> None:
    sig = sign_payload(b"x", b"k")
    assert verify_signature(b"y", b"k", sig) is False


def test_verify_signature_rejects_bad_prefix() -> None:
    sig = sign_payload(b"x", b"k").removeprefix("v1=")
    assert verify_signature(b"x", b"k", sig) is False
    assert verify_signature(b"x", b"k", "v2=" + sig) is False
    assert verify_signature(b"x", b"k", "") is False


def test_sign_payload_rejects_str_inputs() -> None:
    with pytest.raises(TypeError):
        sign_payload("not-bytes", b"k")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        sign_payload(b"x", "not-bytes")  # type: ignore[arg-type]
