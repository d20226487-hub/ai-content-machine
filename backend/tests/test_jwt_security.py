"""PyJWT roundtrip + tamper detection.

These tests cover the migration from python-jose → PyJWT (CVE-2024-33663,
CVE-2024-33664). Anything that consumed JWTError must continue to work.
"""
from __future__ import annotations

import time

import pytest

from app.core.security import (
    JWTError,
    create_access_token,
    decode_access_token,
)


def test_roundtrip_basic():
    token = create_access_token(42)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert "iat" in payload and "exp" in payload


def test_roundtrip_extra_claims():
    token = create_access_token(7, extra={"role": "admin"})
    payload = decode_access_token(token)
    assert payload["role"] == "admin"


def test_decode_garbage_raises_jwterror():
    with pytest.raises(JWTError):
        decode_access_token("not-a-jwt")


def test_decode_signature_tamper_raises_jwterror():
    token = create_access_token(1)
    # Truncate the signature so verification fails.
    head, body, _ = token.split(".")
    bad = f"{head}.{body}.AAAAAAA"
    with pytest.raises(JWTError):
        decode_access_token(bad)


def test_decode_expired_raises_jwterror(monkeypatch):
    # Force a token whose `exp` is already in the past.
    import jwt as _pyjwt

    from app.core import security as security_mod

    payload = {
        "sub": "1",
        "iat": int(time.time()) - 7200,
        "exp": int(time.time()) - 3600,
    }
    token = _pyjwt.encode(
        payload,
        security_mod.settings.JWT_SECRET,
        algorithm=security_mod.settings.JWT_ALG,
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_decode_alg_none_attack_blocked():
    """Classic ``alg=none`` confused-deputy attack — must NOT verify."""
    import json
    import base64

    def b64u(d: bytes) -> str:
        return base64.urlsafe_b64encode(d).rstrip(b"=").decode()

    header = b64u(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = b64u(json.dumps({"sub": "1"}).encode())
    forged = f"{header}.{payload}."
    with pytest.raises(JWTError):
        decode_access_token(forged)
