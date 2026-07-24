"""Autotool connection config endpoints (admin + manager).

Separate from app/api/autotool.py (which is the PUBLIC, unauthenticated CSV
route) — this router is fully auth-gated. It backs the Autotool tab under
/publish: set + test the X-Api-Key and target ImportPosts URL used to hand off
exported tables to the external Autotool proxy.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_role
from app.db.models import BulkTable, User
from app.db.session import get_db
from app.schemas.autotool import (
    AutotoolConfigRead,
    AutotoolConfigUpdate,
    AutotoolPostPreview,
    AutotoolRunCreate,
    AutotoolRunDetail,
    AutotoolRunsPage,
    AutotoolTablesPage,
    AutotoolTestResult,
)
from app.services import autotool_config as svc
from app.services import autotool_run as run_svc
from app.tasks.autotool_run import seed_autotool_run

router = APIRouter(prefix="/autotool", tags=["autotool"])


@router.get("/config", response_model=AutotoolConfigRead)
async def get_autotool_config(
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolConfigRead:
    return await svc.read_config(db)


@router.put("/config", response_model=AutotoolConfigRead)
async def put_autotool_config(
    payload: AutotoolConfigUpdate,
    actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolConfigRead:
    return await svc.update_config(db, payload, actor.id)


@router.post("/config/test", response_model=AutotoolTestResult)
async def test_autotool_config(
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolTestResult:
    return await svc.test_connection(db)


@router.get("/tables", response_model=AutotoolTablesPage)
async def list_shared_tables(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolTablesPage:
    """Tables currently exposed to Autotool, paginated."""
    return await svc.list_shared_tables(db, page, page_size)


@router.get("/tables/{table_id}/post-preview", response_model=AutotoolPostPreview)
async def autotool_post_preview(
    table_id: int,
    site_column_id: int | None = Query(default=None),
    page_size: int | None = Query(default=None, ge=1, le=1000),
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolPostPreview:
    """Preview the ImportPosts POST request for one shared table."""
    t = (
        (
            await db.execute(
                select(BulkTable)
                .where(
                    BulkTable.id == table_id,
                    BulkTable.autotool_enabled.is_(True),
                    BulkTable.deleted_at.is_(None),
                )
                .options(selectinload(BulkTable.columns))
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return await svc.build_post_preview(db, t, site_column_id, page_size)


@router.post("/runs", response_model=AutotoolRunDetail, status_code=status.HTTP_201_CREATED)
async def create_autotool_run(
    payload: AutotoolRunCreate,
    actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolRunDetail:
    """Create a background send run for a shared table and enqueue it.

    This will fire ImportPosts POSTs to live sites — the UI confirms first, then
    redirects to the run's progress page.
    """
    t = (
        (
            await db.execute(
                select(BulkTable)
                .where(
                    BulkTable.id == payload.table_id,
                    BulkTable.autotool_enabled.is_(True),
                    BulkTable.deleted_at.is_(None),
                )
                .options(selectinload(BulkTable.columns))
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    run = await run_svc.create_run(
        db,
        t,
        payload.site_column_id,
        payload.page_size,
        actor.id,
        acknowledge_append=payload.acknowledge_append,
    )
    seed_autotool_run.delay(run.id)
    return await run_svc.get_run_detail(db, run.id, 1, 50)


@router.get("/runs", response_model=AutotoolRunsPage)
async def list_autotool_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolRunsPage:
    return await run_svc.list_runs(db, page, page_size)


@router.get("/runs/{run_id}", response_model=AutotoolRunDetail)
async def get_autotool_run(
    run_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolRunDetail:
    return await run_svc.get_run_detail(db, run_id, page, page_size)


@router.post("/runs/{run_id}/cancel", response_model=AutotoolRunDetail)
async def cancel_autotool_run(
    run_id: int,
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolRunDetail:
    return await run_svc.cancel_run(db, run_id)


@router.post("/runs/{run_id}/retry-failed", response_model=AutotoolRunDetail)
async def retry_failed_autotool_run(
    run_id: int,
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolRunDetail:
    await run_svc.retry_failed(db, run_id)
    seed_autotool_run.delay(run_id)
    return await run_svc.get_run_detail(db, run_id, 1, 50)
