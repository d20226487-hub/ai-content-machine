"""JWT + password hashing.

JWT layer uses PyJWT (``pyjwt``). The previous ``python-jose`` package is
unmaintained with public CVEs (CVE-2024-33663, CVE-2024-33664). PyJWT's
``decode`` raises subclasses of ``InvalidTokenError`` (expiration,
signature, malformed, etc.) — we re-export it as ``JWTError`` so call sites
that ``except JWTError`` keep working unchanged.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as _pyjwt
from jwt import InvalidTokenError as JWTError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(subject: str | int, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return _pyjwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raise JWTError on invalid/expired tokens."""
    return _pyjwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "JWTError",
]
