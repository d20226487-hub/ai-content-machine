"""Celery task that runs the async bulk-generation service.

Each task processes a single (row, column) cell. Worker concurrency is
configured in docker-compose (default 4 in flight).

Important: we create a fresh async engine + session inside each task. The
global SessionLocal in app.db.session binds connections to whatever event loop
first touched it; asyncio.run() in a Celery task starts a brand new loop, and
pooled asyncpg connections from the previous loop blow up with
"Future attached to a different loop". A NullPool engine per task is the
simplest fix and the cost is one connection per task — fine for our volume.
"""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.bulk_generation import generate_one_cell
from app.tasks.celery_app import celery_app


@celery_app.task(name="bulk.generate_cell")
def generate_bulk_cell(table_id: int, row_id: int, column_id: int) -> dict:
    asyncio.run(_run(table_id, row_id, column_id))
    return {"table_id": table_id, "row_id": row_id, "column_id": column_id, "ok": True}


async def _run(table_id: int, row_id: int, column_id: int) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    SessionPerTask: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with SessionPerTask() as db:
            await generate_one_cell(
                db, table_id=table_id, row_id=row_id, column_id=column_id
            )
    finally:
        await engine.dispose()
