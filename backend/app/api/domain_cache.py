"""Bulk Custom-CMS cache clear/warm runs (admin + manager).

Mounted at ``/domains/cache/*`` (three+ path segments, so it never collides
with the ``/domains/{domain_id}`` routes on the domains router). Mirrors the
Bulk Runs / Autotool Runs control surface: create → seed; list; get;
cancel; retry-failed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.models import User
from app.db.session import get_db
from app.schemas.domain_cache import (
    DomainCacheRunCreate,
    DomainCacheRunDetail,
    DomainCacheRunsPage,
)
from app.services import domain_cache as svc
from app.tasks.domain_cache import seed_domain_cache_run

router = APIRouter(
    prefix="/domains/cache",
    tags=["domain-cache"],
    dependencies=[Depends(require_role("admin", "manager"))],
)


@router.post("/runs", response_model=DomainCacheRunDetail, status_code=201)
async def create_cache_run(
    payload: DomainCacheRunCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> DomainCacheRunDetail:
    run = await svc.create_run(db, payload.domain_ids, payload.action, actor.id)
    seed_domain_cache_run.delay(run.id)
    return await svc.get_run_detail(db, run.id, 1, 50)


@router.get("/runs", response_model=DomainCacheRunsPage)
async def list_cache_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> DomainCacheRunsPage:
    return await svc.list_runs(db, page, page_size)


@router.get("/runs/{run_id}", response_model=DomainCacheRunDetail)
async def get_cache_run(
    run_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> DomainCacheRunDetail:
    return await svc.get_run_detail(db, run_id, page, page_size)


@router.post("/runs/{run_id}/cancel", response_model=DomainCacheRunDetail)
async def cancel_cache_run(
    run_id: int, db: AsyncSession = Depends(get_db)
) -> DomainCacheRunDetail:
    return await svc.cancel_run(db, run_id)


@router.post("/runs/{run_id}/retry-failed", response_model=DomainCacheRunDetail)
async def retry_failed_cache_run(
    run_id: int, db: AsyncSession = Depends(get_db)
) -> DomainCacheRunDetail:
    await svc.retry_failed(db, run_id)
    seed_domain_cache_run.delay(run_id)
    return await svc.get_run_detail(db, run_id, 1, 50)
