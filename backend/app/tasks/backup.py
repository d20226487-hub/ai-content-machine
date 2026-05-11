"""Celery task wrapping the backup service.

Schedule: daily at 03:00 UTC, configured in `celery_app.beat_schedule`. The
task is also invoked manually from the admin UI ("Run backup now").
"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.backup import perform_backup, should_run_scheduled_now
from app.tasks.celery_app import celery_app


@celery_app.task(name="backup.run")
def run_backup_task(trigger: str = "scheduled") -> dict:
    """Run a backup. `trigger` decides semantics:
      * 'manual' — always runs; the user clicked "Run backup now".
      * 'scheduled' — fires hourly from beat. The task body checks the user's
        configured hour-of-day and skips silently the other 23 firings."""
    return asyncio.run(_run(trigger))


async def _run(trigger: str) -> dict:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    SessionPerTask: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with SessionPerTask() as db:
            if trigger == "scheduled" and not await should_run_scheduled_now(db):
                return {"trigger": trigger, "ran": False}
            await perform_backup(db, trigger=trigger)
            return {"trigger": trigger, "ran": True}
    finally:
        await engine.dispose()
