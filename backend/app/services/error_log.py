"""Centralized error capture.

Two entry points:

- ``log_error(session, ...)`` — when caller already holds an AsyncSession.
  Used by FastAPI endpoints and request-scoped middleware that haven't
  yet rolled back.

- ``log_error_standalone(...)`` — creates its own short-lived NullPool
  engine + session. Use from Celery task signal handlers, exception
  handlers running after the request session was rolled back, and
  anywhere else there is no live session to share.

Both never raise: if writing the error fails, we fall back to stderr so
the original error path isn't masked by a logging failure.

After every successful insert we probabilistically trigger retention
cleanup (1% chance per write). On a moderately busy system that runs
roughly daily; on a quiet system the manual "Purge old" button covers it.
"""
from __future__ import annotations

import logging
import random
import sys
import traceback
from typing import Any

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import AppSetting, ErrorLog

logger = logging.getLogger(__name__)

CLEANUP_PROBABILITY = 0.01
DEFAULT_RETENTION_DAYS = 30
ALLOWED_RETENTION_DAYS = (7, 14, 30, 90)


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _coerce_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    safe: dict[str, Any] = {}
    for k, v in context.items():
        try:
            import json
            json.dumps(v, default=str)
            safe[str(k)] = v
        except Exception:
            safe[str(k)] = repr(v)
    return safe


async def log_error(
    session: AsyncSession,
    *,
    source: str,
    category: str,
    message: str,
    user_id: int | None = None,
    provider: str | None = None,
    status_code: int | None = None,
    context: dict[str, Any] | None = None,
    stack_trace: str | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    commit: bool = True,
) -> int | None:
    """Insert an error log row using an existing session. Never raises."""
    try:
        row = ErrorLog(
            source=source,
            category=category,
            message=_truncate(message, 4000) or "(empty)",
            user_id=user_id,
            provider=provider,
            status_code=status_code,
            context_json=_coerce_context(context),
            stack_trace=_truncate(stack_trace, 20000),
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
        )
        session.add(row)
        if commit:
            await session.commit()
            await session.refresh(row)
        else:
            await session.flush()

        if random.random() < CLEANUP_PROBABILITY:
            try:
                await _purge_old(session, commit=commit)
            except Exception:
                pass

        return row.id
    except Exception:
        traceback.print_exc(file=sys.stderr)
        try:
            await session.rollback()
        except Exception:
            pass
        return None


async def log_error_standalone(
    *,
    source: str,
    category: str,
    message: str,
    user_id: int | None = None,
    provider: str | None = None,
    status_code: int | None = None,
    context: dict[str, Any] | None = None,
    stack_trace: str | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
) -> int | None:
    """Insert an error log row using a fresh, disposable engine. Never raises."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            return await log_error(
                session,
                source=source,
                category=category,
                message=message,
                user_id=user_id,
                provider=provider,
                status_code=status_code,
                context=context,
                stack_trace=stack_trace,
                resource_type=resource_type,
                resource_id=resource_id,
            )
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return None
    finally:
        try:
            await engine.dispose()
        except Exception:
            pass


async def get_retention_days(session: AsyncSession) -> int:
    result = await session.execute(
        select(AppSetting.value).where(AppSetting.key == "error_log_retention_days")
    )
    value = result.scalar_one_or_none()
    if isinstance(value, int) and value in ALLOWED_RETENTION_DAYS:
        return value
    return DEFAULT_RETENTION_DAYS


async def set_retention_days(
    session: AsyncSession, days: int, updated_by_id: int | None
) -> int:
    if days not in ALLOWED_RETENTION_DAYS:
        raise ValueError(
            f"retention must be one of {ALLOWED_RETENTION_DAYS}, got {days}"
        )
    setting = await session.get(AppSetting, "error_log_retention_days")
    if setting is None:
        setting = AppSetting(key="error_log_retention_days", value=days)
        session.add(setting)
    else:
        setting.value = days
    setting.updated_by_id = updated_by_id
    await session.commit()
    return days


async def _purge_old(session: AsyncSession, *, commit: bool) -> int:
    days = await get_retention_days(session)
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(days))
    result = await session.execute(
        delete(ErrorLog).where(ErrorLog.created_at < cutoff)
    )
    if commit:
        await session.commit()
    return result.rowcount or 0


async def purge_old(session: AsyncSession) -> int:
    """Manual retention purge. Returns number of rows deleted."""
    return await _purge_old(session, commit=True)
