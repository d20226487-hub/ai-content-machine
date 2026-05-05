"""Fernet encryption helpers with key-rotation support.

The module-level `_fernet` is a `MultiFernet` over `Settings.fernet_keys_list`.
With a single key it behaves exactly like a plain `Fernet` (so existing
deployments that only set `FERNET_KEY` see no change). With multiple keys:

    * encrypt() always uses the FIRST key in the list (the "primary").
    * decrypt() tries each key in order until one succeeds.
    * rotate() re-encrypts a token under the primary key — useful for a
      rotation script that walks every encrypted row.

Rotation workflow:
    1. Generate a new key:
           python -c "from cryptography.fernet import Fernet; \\
                       print(Fernet.generate_key().decode())"
    2. Set `FERNET_KEYS="<new>,<old>"` in .env (primary first, old kept).
    3. Restart api + worker. New writes use <new>. Existing ciphertext
       (encrypted with <old>) still decrypts.
    4. Re-encrypt at leisure — see `rotate()` below — then drop <old>.
"""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings

settings = get_settings()

# `MultiFernet` requires at least one key. With a single key it's effectively
# a plain Fernet — so single-key deployments don't pay any complexity tax.
_fernet = MultiFernet([Fernet(k.encode()) for k in settings.fernet_keys_list])


def encrypt(plaintext: str) -> str:
    """Encrypt a string under the PRIMARY key and return its base64 token."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token, trying every configured key.

    Raises cryptography.fernet.InvalidToken if no key in the list can decrypt
    it (e.g. the ciphertext predates every key currently configured).
    """
    return _fernet.decrypt(token.encode()).decode()


def rotate(token: str) -> str:
    """Re-encrypt an existing token under the primary key.

    Used by rotation scripts that walk every encrypted row to migrate them
    from the old key to the new primary. Callers should be ready to handle
    InvalidToken if a row is corrupt.
    """
    return _fernet.rotate(token.encode()).decode()


__all__ = ["encrypt", "decrypt", "rotate", "InvalidToken"]
