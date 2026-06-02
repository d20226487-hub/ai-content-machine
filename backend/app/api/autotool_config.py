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
    AutotoolSendResult,
    AutotoolTablesPage,
    AutotoolTestResult,
)
from app.services import autotool_config as svc

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
    return await svc.build_post_preview(db, t, site_column_id)


@router.post("/tables/{table_id}/send", response_model=AutotoolSendResult)
async def send_table_to_autotool(
    table_id: int,
    site_column_id: int | None = Query(default=None),
    _actor: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> AutotoolSendResult:
    """Fire one ImportPosts POST per domain for a shared table.

    This actually triggers publishing on the target sites — the UI confirms
    with the user before calling it.
    """
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
    return await svc.send_table(db, t, site_column_id)
