"""Sanity test for Fernet key rotation. Run inside the backend prod image:

    docker run --rm -v $(pwd):/app -w /app acm-backend:prod-test \
        python test_fernet_rotation.py

Exits 0 on success, 1 on failure. Not part of the application — kept here as
a self-contained smoke for the rotation logic introduced in Blocker 5.
"""
from __future__ import annotations

import importlib
import os
import sys


def _reload_crypto():
    """Drop cached app.* modules so the next import re-reads env."""
    for mod in [m for m in list(sys.modules) if m.startswith("app.")]:
        del sys.modules[mod]
    return importlib.import_module("app.core.crypto")


def main() -> int:
    from cryptography.fernet import Fernet, InvalidToken

    k_old = Fernet.generate_key().decode()
    k_new = Fernet.generate_key().decode()

    # Required-but-unused settings for module import.
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://x:x@x/x"
    os.environ["JWT_SECRET"] = "test-secret"

    # ---- Case 1: backward-compatible single FERNET_KEY ----
    os.environ.pop("FERNET_KEYS", None)
    os.environ["FERNET_KEY"] = k_old
    crypto = _reload_crypto()

    token_under_old = crypto.encrypt("payload-A")
    assert crypto.decrypt(token_under_old) == "payload-A", "single-key roundtrip"
    print("[case 1] single FERNET_KEY: OK")

    # ---- Case 2: rotation period — FERNET_KEYS="<new>,<old>" ----
    os.environ.pop("FERNET_KEY", None)
    os.environ["FERNET_KEYS"] = f"{k_new},{k_old}"
    crypto = _reload_crypto()

    # Old ciphertext (encrypted under k_old) must still decrypt thanks to the
    # second key in the list.
    assert crypto.decrypt(token_under_old) == "payload-A", "old token still readable"

    # New writes go under the primary (k_new) — verify by checking that an
    # operator who later drops k_old can still read what we wrote now.
    token_under_new = crypto.encrypt("payload-B")
    assert crypto.decrypt(token_under_new) == "payload-B", "new write roundtrip"

    # rotate() re-encrypts a token under the primary key. After rotate(), the
    # ciphertext changes and is decryptable when only k_new is configured.
    rotated_token = crypto.rotate(token_under_old)
    assert rotated_token != token_under_old, "rotate produces new ciphertext"
    assert crypto.decrypt(rotated_token) == "payload-A", "rotated token decrypts"
    print("[case 2] FERNET_KEYS=new,old (rotation period): OK")

    # ---- Case 3: post-rotation — only k_new configured ----
    os.environ["FERNET_KEYS"] = k_new
    crypto = _reload_crypto()

    # Tokens that were rotated survive; tokens still under the dropped key don't.
    assert crypto.decrypt(rotated_token) == "payload-A", "rotated token survives drop"
    assert crypto.decrypt(token_under_new) == "payload-B", "new-key write survives drop"
    try:
        crypto.decrypt(token_under_old)
        print("FAIL: token under dropped key should NOT decrypt")
        return 1
    except InvalidToken:
        pass  # expected
    print("[case 3] FERNET_KEYS=new (k_old dropped): OK")

    # ---- Case 4: validation — neither set ----
    os.environ.pop("FERNET_KEY", None)
    os.environ.pop("FERNET_KEYS", None)
    try:
        _reload_crypto()
        print("FAIL: missing keys should raise")
        return 1
    except ValueError as e:
        assert "FERNET_KEY" in str(e), "error message mentions the env var"
    print("[case 4] no keys configured raises ValueError: OK")

    print("\nAll Fernet-rotation cases pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
