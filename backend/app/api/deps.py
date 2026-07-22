import secrets
from collections.abc import Iterable

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import JWTError, decode_access_token
from app.db.models import User
from app.db.session import get_db

# tokenUrl is the URL clients use to get a token; documented in OpenAPI.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active or user.deleted_at is not None:
        # Trashed users get the same 401 as inactive users — the next
        # request after they're moved to Trash kicks them out instead of
        # waiting for their JWT to expire. Restored users have to log in
        # fresh (we don't reissue their old token).
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


def require_role(*allowed: str):
    """Dependency factory: only allow users whose role.name is in `allowed`."""

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed)}",
            )
        return user

    return _check


def require_any_of(roles: Iterable[str]):
    return require_role(*roles)


async def require_ingest_api_key(
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    """Static shared-secret auth for the machine-to-machine ingest endpoints.

    Accepts the key via ``X-Api-Key: <key>`` or ``Authorization: Bearer <key>``.
    Disabled (503) until ``CSV_INGEST_API_KEY`` is configured, so the feature is
    off by default. Constant-time compare avoids leaking the key via timing.
    """
    expected = get_settings().CSV_INGEST_API_KEY
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CSV ingest is not configured (set CSV_INGEST_API_KEY).",
        )
    provided = x_api_key
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
