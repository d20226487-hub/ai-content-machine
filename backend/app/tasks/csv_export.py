"""Celery wrappers for background CSV export jobs.

Fresh async engine + session per task (NullPool), per the codebase pattern.
``csv_export.build`` builds + stores one job's gzipped CSV; ``csv_export.cleanup``
(beat) drops expired jobs.
"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.tasks.celery_app import celery_app


@celery_app.task(name="csv_export.build")
def build_csv_export(job_id: int) -> dict:
    outcome = asyncio.run(_build(job_id))
    return {"job_id": job_id, "outcome": outcome}


@celery_app.task(name="csv_export.cleanup")
def cleanup_csv_exports() -> dict:
    deleted = asyncio.run(_cleanup())
    return {"deleted": deleted}


def _make_session():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    return engine, Session


async def _build(job_id: int) -> str:
    from app.services.csv_export import build_job

    engine, Session = _make_session()
    try:
        async with Session() as db:
            return await build_job(db, job_id)
    finally:
        await engine.dispose()


async def _cleanup() -> int:
    from app.services.csv_export import cleanup_old_jobs

    engine, Session = _make_session()
    try:
        async with Session() as db:
            return await cleanup_old_jobs(db)
    finally:
        await engine.dispose()
