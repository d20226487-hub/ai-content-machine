"""Celery task wrapping a single non-bulk publish.

Per the project's existing pattern, every Celery task creates its own async
engine + sessionmaker (NullPool) so the task's fresh asyncio loop owns the
async resources cleanly. See ``app/tasks/bulk_generation.py`` for the same
pattern.
"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.tasks.celery_app import celery_app


@celery_app.task(name="publish.publish_one_single")
def publish_one_single(job_id: int) -> dict:
    asyncio.run(_run(job_id))
    return {"job_id": job_id, "ok": True}


async def _run(job_id: int) -> None:
    from app.services.publish_single import process_single_job

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with Session() as db:
            await process_single_job(db, job_id=job_id)
    finally:
        await engine.dispose()
