"""Machine-to-machine ingest API.

A static-key-authenticated surface for other systems to push data INTO the app
without a user login. Today it's a single endpoint — ``POST /ingest/csv-tables``
turns a CSV sent in the request body into a Library bulk table. Auth is the
shared ``CSV_INGEST_API_KEY`` (via ``X-Api-Key`` or ``Authorization: Bearer``);
the whole router is disabled (503) until that key is configured.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_ingest_api_key
from app.core.config import get_settings
from app.db.models import BulkTableColumn, BulkTableFolder, BulkTableRow, User
from app.db.session import get_db
from app.schemas.bulk import CsvIngestResult
from app.services.csv_import import CsvImportError, build_table_from_csv

router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
    dependencies=[Depends(require_ingest_api_key)],
)


async def _resolve_owner(db: AsyncSession, owner_id: int | None) -> int | None:
    """The configured owner id if it points at a live user, else None (no
    owner — admins/managers still see the table)."""
    if owner_id is None:
        return None
    return await db.scalar(
        select(User.id).where(User.id == owner_id, User.deleted_at.is_(None))
    )


async def _resolve_folder(db: AsyncSession, folder_id: int | None) -> int | None:
    """The configured folder id if it exists, else None (Library root)."""
    if folder_id is None:
        return None
    return await db.scalar(
        select(BulkTableFolder.id).where(BulkTableFolder.id == folder_id)
    )


@router.post(
    "/csv-tables",
    response_model=CsvIngestResult,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_csv_table(
    request: Request,
    name: str | None = Query(
        default=None, description="Table name. Omit for an auto timestamped name."
    ),
    delimiter: str = Query(default=",", description="Single char, or \\t for tab."),
    has_header: bool = Query(
        default=True, description="First row holds column names."
    ),
    db: AsyncSession = Depends(get_db),
) -> CsvIngestResult:
    """Create a Library bulk table from a CSV sent in the request body.

    The CSV is the raw request body (``Content-Type: text/csv``); options ride
    in the query string. Auth: ``X-Api-Key: <key>`` or
    ``Authorization: Bearer <key>``. The new table is owned by
    ``CSV_INGEST_OWNER_ID`` and lands in ``CSV_INGEST_FOLDER_ID`` when those are
    set (else no owner / Library root).

        curl -X POST "$BASE/ingest/csv-tables?name=Leads" \\
             -H "X-Api-Key: $KEY" -H "Content-Type: text/csv" \\
             --data-binary @leads.csv
    """
    raw = await request.body()
    settings = get_settings()
    table_name = (name or "").strip() or (
        f"CSV import {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}"
    )
    owner_id = await _resolve_owner(db, settings.CSV_INGEST_OWNER_ID)
    folder_id = await _resolve_folder(db, settings.CSV_INGEST_FOLDER_ID)

    try:
        t = await build_table_from_csv(
            db,
            name=table_name,
            raw=raw,
            delimiter=delimiter,
            has_header=has_header,
            folder_id=folder_id,
            created_by_id=owner_id,
        )
    except CsvImportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    columns = await db.scalar(
        select(func.count())
        .select_from(BulkTableColumn)
        .where(BulkTableColumn.table_id == t.id)
    )
    rows = await db.scalar(
        select(func.count())
        .select_from(BulkTableRow)
        .where(BulkTableRow.table_id == t.id)
    )
    return CsvIngestResult(
        table_id=t.id, name=t.name, columns=int(columns or 0), rows=int(rows or 0)
    )
