import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserRead
from app.services import login_throttle

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Best-effort client IP for throttling.

    In prod uvicorn runs with ``--proxy-headers --forwarded-allow-ips=*``
    behind Caddy, so ``request.client.host`` already reflects the original
    client address. Fall through to ``"unknown"`` for the (vanishingly rare)
    case where the ASGI scope has no client tuple — better to throttle one
    bucket of unknown-IP attempts than to crash the login.
    """
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    ip = _client_ip(request)
    email = payload.email

    # 1. Throttle gate. Block early so brute-forcers can't even reach the DB
    # query, and so we don't pay the bcrypt cost on every blocked attempt.
    verdict = await login_throttle.check(ip=ip, email=email)
    if not verdict.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again later.",
            headers={"Retry-After": str(verdict.retry_after_seconds)},
        )

    # 2. Look up the user. Always run the bcrypt verify even on miss so the
    # response time is the same in both cases (timing-attack mitigation).
    # Filter `deleted_at IS NULL` at the query: the partial-unique index on
    # email allows one trashed + one active row to share an address, so
    # without this filter `.scalar_one_or_none()` would raise
    # MultipleResultsFound → 500. Trashed rows can't log in regardless.
    user = (
        await db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()

    # bcrypt is CPU-heavy (~100–300 ms per verify). Off-load to a worker
    # thread so the asyncio event loop stays free to serve other requests
    # during the verify; otherwise N concurrent logins serialize the loop.
    if user is None:
        # Burn the same time a real verify would, against a known-bad hash,
        # so attackers can't distinguish "no such user" from "wrong password"
        # by timing. The hash is a one-time bcrypt of an unguessable string;
        # it must be syntactically valid or passlib raises before doing the
        # round count of work.
        _DUMMY_HASH = (
            "$2b$12$N/jgNSuJpJF6Z3uKXGDsXO8u4hvjBFNcvAY8ICCkuMOGLvQVRPi.K"
        )
        await asyncio.to_thread(verify_password, payload.password, _DUMMY_HASH)
        password_ok = False
    else:
        password_ok = await asyncio.to_thread(
            verify_password, payload.password, user.password_hash
        )

    if user is None or not password_ok:
        await login_throttle.record_failure(ip=ip, email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if not user.is_active or user.deleted_at is not None:
        # Trashed users can't log back in; their account is only
        # recoverable by an admin via /users/trash → Restore.
        await login_throttle.record_failure(ip=ip, email=email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    # Successful login: clear the per-email counter so a user who fat-fingered
    # a few times then got it right isn't still close to lockout.
    await login_throttle.reset_email(email)

    token = create_access_token(subject=user.id, extra={"role": user.role.name})
    return TokenResponse(access_token=token, expires_in=settings.JWT_EXPIRE_MINUTES * 60)


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
