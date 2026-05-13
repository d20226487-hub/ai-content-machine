"""Periodic cleanup of trashed soft-deletable entities.

Handles multiple entity types in one daily pass, each with its own
retention setting in ``app_settings``:

  bulk_tables → ``bulk_table_trash_retention_days`` (default 50)
  domains     → ``domain_trash_retention_days``     (default 50)

A retention of ``0`` disables auto-empty for that entity — trashed rows
stay until an admin manually empties them from the per-entity trash
page. Each entity's check is independent; one disabled retention doesn't
affect the others.

Scheduled daily at 03:15 UTC (see ``celery_app.beat_schedule``). Daily
cadence is plenty given retention is measured in days; admins who need
an immediate empty can hit "Empty trash" on the relevant trash page.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import AppSetting, BulkTable, Domain, Prompt, Role, User
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 50


@dataclass(frozen=True)
class _EntitySpec:
    """One soft-deletable entity to scan during cleanup."""

    name: str  # for logging
    model: type
    setting_key: str
    # When True, delete via ORM per-row instead of bulk SQL DELETE. Slower
    # but lets SQLAlchemy run the per-row mutations needed to untangle
    # circular FKs (Prompt has `current_version_id` pointing at
    # `prompt_versions.id`, which has to be NULLed before the cascade can
    # walk through cleanly).
    per_row_delete: bool = False


# Registry of entities cleaned by this task. Add new entries as more
# entities become soft-deletable (prompts, users).
_ENTITIES: tuple[_EntitySpec, ...] = (
    _EntitySpec(name="bulk_tables", model=BulkTable, setting_key="bulk_table_trash_retention_days"),
    _EntitySpec(name="domains",     model=Domain,    setting_key="domain_trash_retention_days"),
    _EntitySpec(
        name="prompts", model=Prompt, setting_key="prompt_trash_retention_days",
        per_row_delete=True,
    ),
    # Users always go through per_row_delete so we can apply the admin
    # safeguard: never auto-purge a trashed admin (matches the API-side
    # `empty_trash` endpoint). The cleanup is genuinely irrecoverable
    # for users — credentials + audit trails go with them — so the
    # "are you sure" bar is set higher than for the other entities.
    _EntitySpec(
        name="users", model=User, setting_key="user_trash_retention_days",
        per_row_delete=True,
    ),
)


@celery_app.task(name="trash.cleanup")
def trash_cleanup() -> dict:
    return asyncio.run(_run())


async def _run() -> dict:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    summary: dict[str, dict] = {}
    try:
        async with Session() as db:
            for spec in _ENTITIES:
                summary[spec.name] = await _cleanup_one(db, spec)
        return summary
    finally:
        await engine.dispose()


async def _cleanup_one(db: AsyncSession, spec: _EntitySpec) -> dict:
    days = await _load_retention_days(db, spec.setting_key)
    if days <= 0:
        return {"deleted": 0, "retention_days": days, "skipped": True}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    if spec.per_row_delete:
        # ORM path for entities with quirks: circular FKs (Prompt) or
        # safety guards (User → skip admins). Fetch the eligible rows,
        # apply quirks, then delete one by one. Slower than bulk DELETE
        # but nightly retention runs rarely have many rows to expire.
        stmt = select(spec.model).where(
            spec.model.deleted_at.is_not(None),
            spec.model.deleted_at < cutoff,
        )
        # User-specific: never auto-purge admins. Same posture as the
        # API-side empty_trash endpoint.
        if spec.model is User:
            stmt = stmt.join(Role, Role.id == User.role_id).where(
                Role.name != "admin"
            )
        rows = (await db.execute(stmt)).scalars().all()
        # Prompt-specific: break the prompts.current_version_id pointer
        # before delete so the cascade through prompt_versions can run.
        if spec.model is Prompt:
            for p in rows:
                p.current_version_id = None
            await db.flush()
        for r in rows:
            await db.delete(r)
        await db.commit()
        n = len(rows)
    else:
        result = await db.execute(
            sa_delete(spec.model).where(
                spec.model.deleted_at.is_not(None),
                spec.model.deleted_at < cutoff,
            )
        )
        await db.commit()
        n = int(result.rowcount or 0)

    if n:
        log.info(
            "trash.cleanup deleted %d %s row(s) older than %d days",
            n, spec.name, days,
        )
    return {"deleted": n, "retention_days": days}


async def _load_retention_days(db: AsyncSession, key: str) -> int:
    """Read the retention setting. Missing / non-numeric → default."""
    row = (
        await db.execute(
            select(AppSetting.value).where(AppSetting.key == key)
        )
    ).scalar_one_or_none()
    if row is None:
        return DEFAULT_RETENTION_DAYS
    try:
        return max(0, int(row))
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS
