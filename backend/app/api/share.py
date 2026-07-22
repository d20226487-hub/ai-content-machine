"""Public (UNAUTHENTICATED) read surface for cell share links.

``GET /share/{token}`` returns one bulk-table cell's current content so someone
without an ACM account can read it. The token is the only credential, so this
module is deliberately paranoid:

  * every failure mode (unknown token / revoked / expired / trashed table /
    deleted row-column) returns the SAME generic 404, so a probe can't tell a
    real-but-expired token from a wrong one;
  * only the cell's content plus a column label and row number are returned —
    never the table name, the owner, or anything else about the workspace;
  * the content is rendered client-side inside a fully sandboxed iframe (see
    the /share page), so AI-generated HTML can't execute against our origin.

Mounted OUTSIDE the authenticated routers — see app/main.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BulkTable,
    BulkTableCell,
    BulkTableColumn,
    BulkTableRow,
    CellShareLink,
)
from app.db.session import get_db
from app.schemas.share import SharedCellRead

router = APIRouter(prefix="/share", tags=["share"])


def _gone() -> HTTPException:
    """One indistinguishable 404 for every reason a link might not resolve."""
    return HTTPException(status_code=404, detail="This link is not available.")


@router.get("/{token}", response_model=SharedCellRead)
async def get_shared_cell(
    token: str, db: AsyncSession = Depends(get_db)
) -> SharedCellRead:
    """The cell's CURRENT content for a live share link, or 404."""
    link = (
        await db.execute(
            select(CellShareLink).where(CellShareLink.token == token)
        )
    ).scalar_one_or_none()
    if link is None or link.revoked_at is not None:
        raise _gone()
    if link.expires_at <= datetime.now(timezone.utc):
        raise _gone()

    # A trashed table's content goes private again.
    table = await db.get(BulkTable, link.table_id)
    if table is None or table.deleted_at is not None:
        raise _gone()

    col = await db.get(BulkTableColumn, link.column_id)
    row = await db.get(BulkTableRow, link.row_id)
    if col is None or row is None:
        raise _gone()

    value = (
        await db.execute(
            select(BulkTableCell.value).where(
                BulkTableCell.row_id == link.row_id,
                BulkTableCell.column_id == link.column_id,
            )
        )
    ).scalar_one_or_none()

    return SharedCellRead(
        content=value or "",
        column_name=col.name,
        row_number=row.position + 1,
        expires_at=link.expires_at,
    )
