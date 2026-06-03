"""Bulk-generation tables.

Visibility:
  * content_generator — only their own tables
  * manager           — sees all tables; read + edit; can only DELETE tables they own
  * admin             — sees all tables; full access (read + edit + delete on any)

Each route gates access through `_get_table_or_404(level=...)`. The list
endpoint short-circuits the owner filter for manager/admin.
"""
import csv
import io
import uuid
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from datetime import datetime, timezone

from app.api.deps import get_current_user, require_role
from app.db.models import (
    AppSetting,
    BulkGenerationRun,
    BulkPublishRun,
    BulkTable,
    BulkTableCell,
    BulkTableColumn,
    BulkTableFolder,
    BulkTableRow,
    FindReplaceRun,
    LinkCheckCrawlTarget,
    LinkCheckRun,
    LinkCheckViolation,
    LinkFixCell,
    LinkFixRun,
    StructureFormatCell,
    StructureFormatRun,
    User,
)
from app.db.session import get_db
from app.schemas.bulk import (
    AutotoolState,
    BulkGenerationRunDetail,
    BulkGenerationRunRead,
    CellsBatchUpsert,
    CellUpsert,
    ClearValuesRequest,
    ClearValuesResponse,
    ColumnCreate,
    ColumnRead,
    ColumnUpdate,
    ColumnValuesResponse,
    CsvImportRequest,
    DiffSegment,
    FindReplaceRunDetail,
    FindReplaceRunRead,
    FindRequest,
    FindResponse,
    FolderCreate,
    FolderRead,
    FolderUpdate,
    GeneratePreviewResponse,
    GenerateRequest,
    GenerateResponse,
    LinkCheckRequest,
    LinkCheckRunDetail,
    LinkCheckRunRead,
    LinkFixCellRead,
    LinkFixDefaultPrompt,
    LinkFixRequest,
    LinkFixRunDetail,
    LinkFixRunRead,
    LinkViolationRead,
    MatchedCell,
    ReplacedCell,
    ReplaceRequest,
    RowRead,
    RunRename,
    StructureFormatCell as StructureFormatCellSchema,
    StructureFormatPreview,
    StructureFormatPreviewCell,
    StructureFormatRequest,
    StructureFormatRunDetail,
    StructureFormatRunRead,
    TableBulkMove,
    TableCreate,
    TableFixedCell,
    UnifiedSegment,
    TableListItem,
    TableListResponse,
    TranslationCheckConfig,
    TranslationTableResponse,
    TranslationTableRow,
    TableRead,
    TableUpdate,
    TrashBulkIds,
)
from app.services.bulk_csv import build_table_csv
from app.services.find_replace import (
    InvalidPattern,
    apply_replace,
    compile_pattern,
    condense_unified,
    count_matches,
    diff_segments,
    drift_segments,
    segment_diff,
    unified_segments,
)
from app.services.structure_format import (
    OPERATIONS as SF_OPERATIONS,
    apply_operations_traced as sf_apply_traced,
)
from app.tasks.bulk_generation import generate_bulk_cell
from app.tasks.link_check import resume_link_check, seed_link_check
from app.tasks.link_fix import fix_cell as fix_cell_task, resume_link_fix
from app.tasks.structure_format import resume_sf, run_sf

router = APIRouter(
    prefix="/library", tags=["library"], dependencies=[Depends(get_current_user)]
)


# ---------- helpers ----------

AccessLevel = Literal["read", "write", "delete"]


def _role_name(actor: User) -> str:
    return (actor.role.name if actor.role else "") or ""


def _can_access(actor: User, table: BulkTable, level: AccessLevel) -> bool:
    """Effective ACL for one table.

    read/write: owner OR admin OR manager.
    delete:     owner OR admin (managers may NOT delete tables they don't own).
    """
    if table.created_by_id == actor.id:
        return True
    role = _role_name(actor)
    if level == "delete":
        return role == "admin"
    # read or write
    return role in {"admin", "manager"}


async def _get_table_or_404(
    db: AsyncSession,
    table_id: int,
    actor: User,
    *,
    level: AccessLevel = "write",
    full: bool = False,
    include_trashed: bool = False,
) -> BulkTable:
    """Fetch a table by id, enforcing ACL.

    By default `deleted_at IS NULL` is required — trashed tables are invisible
    to every endpoint except the trash surface. Pass ``include_trashed=True``
    when you intentionally want the trashed view (preview, restore,
    permanent delete).
    """
    stmt = select(BulkTable).where(BulkTable.id == table_id)
    if not include_trashed:
        stmt = stmt.where(BulkTable.deleted_at.is_(None))
    if full:
        stmt = stmt.options(
            selectinload(BulkTable.columns),
            selectinload(BulkTable.rows),
        )
    t = (await db.execute(stmt)).unique().scalar_one_or_none()
    if t is None or not _can_access(actor, t, level):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return t


# Back-compat alias kept in case anything still imports the old name; new code
# should use `_get_table_or_404` with an explicit `level=`.
_get_owned_table_or_404 = _get_table_or_404


async def _get_trashed_table_or_404(
    db: AsyncSession,
    table_id: int,
    actor: User,
    *,
    level: AccessLevel = "delete",
    full: bool = False,
) -> BulkTable:
    """Same shape as ``_get_table_or_404`` but for the trash surface.

    Forces ``deleted_at IS NOT NULL`` so the active editor never sees a
    trashed row. Default level is 'delete' since the typical use is
    restore / permanent-delete — read-only preview overrides to 'read'.
    """
    stmt = select(BulkTable).where(
        BulkTable.id == table_id, BulkTable.deleted_at.is_not(None)
    )
    if full:
        stmt = stmt.options(
            selectinload(BulkTable.columns),
            selectinload(BulkTable.rows),
        )
    t = (await db.execute(stmt)).unique().scalar_one_or_none()
    if t is None or not _can_access(actor, t, level):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return t


_ACTIVE_BULK_RUN_STATUSES = ("queued", "running", "paused")


async def _has_active_publish_run(db: AsyncSession, table_id: int) -> int | None:
    """Return the id of an in-flight bulk publish run for this table, if any.

    Used to block soft-delete: trashing a table while it's actively being
    published is too easy a footgun (the run keeps reading the rows, but the
    table is suddenly hidden from /library and from the user). Resolve the
    run first — cancel or wait — then trash.
    """
    rid = (
        await db.execute(
            select(BulkPublishRun.id)
            .where(
                BulkPublishRun.table_id == table_id,
                BulkPublishRun.status.in_(_ACTIVE_BULK_RUN_STATUSES),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return int(rid) if rid is not None else None


def _default_status_for(value: str | None) -> str:
    return "manual" if value not in (None, "") else "empty"


async def _resolve_creator_name(
    db: AsyncSession, created_by_id: int | None
) -> str | None:
    if created_by_id is None:
        return None
    u = await db.get(User, created_by_id)
    if u is None:
        return None
    return (u.full_name or u.email) or None


async def _verify_folder(db: AsyncSession, folder_id: int) -> None:
    f = (
        await db.execute(select(BulkTableFolder.id).where(BulkTableFolder.id == folder_id))
    ).scalar_one_or_none()
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown folder_id",
        )


async def _table_to_read(db: AsyncSession, table: BulkTable) -> TableRead:
    """Build the full TableRead including cells. table must be loaded with columns + rows."""
    row_ids = [r.id for r in table.rows]
    cells = []
    if row_ids:
        cells = (
            (
                await db.execute(
                    select(BulkTableCell).where(BulkTableCell.row_id.in_(row_ids))
                )
            )
            .scalars()
            .all()
        )
    return TableRead.model_validate(
        {
            "id": table.id,
            "name": table.name,
            "description": table.description,
            "folder_id": table.folder_id,
            "created_by_id": table.created_by_id,
            "created_by_name": await _resolve_creator_name(db, table.created_by_id),
            "created_at": table.created_at,
            "updated_at": table.updated_at,
            "autotool_enabled": table.autotool_enabled,
            "autotool_token": table.autotool_token,
            "columns": [ColumnRead.model_validate(c) for c in table.columns],
            "rows": [RowRead.model_validate(r) for r in table.rows],
            "cells": [
                {
                    "id": c.id,
                    "row_id": c.row_id,
                    "column_id": c.column_id,
                    "value": c.value,
                    "status": c.status,
                    "error": c.error,
                    "model_used": c.model_used,
                    "generated_at": c.generated_at,
                    "updated_at": c.updated_at,
                    "translations": c.translations,
                }
                for c in cells
            ],
            "total_row_count": len(table.rows),
        }
    )


async def _table_to_read_paginated(
    db: AsyncSession, table: BulkTable, page: int, page_size: int
) -> TableRead:
    """Build a TableRead for one page of rows.

    Loads all columns (always small) but only the requested page of rows
    (ordered by position) and just the cells belonging to those rows.
    ``total_row_count`` reflects the whole table so the client can render the
    footer / selection math without holding every row. ``table`` only needs
    its scalar attributes loaded — rows/columns are queried here directly so
    we never materialize the full row set."""
    columns = (
        (
            await db.execute(
                select(BulkTableColumn)
                .where(BulkTableColumn.table_id == table.id)
                .order_by(BulkTableColumn.position, BulkTableColumn.id)
            )
        )
        .scalars()
        .all()
    )
    total = (
        await db.execute(
            select(func.count())
            .select_from(BulkTableRow)
            .where(BulkTableRow.table_id == table.id)
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(BulkTableRow)
                .where(BulkTableRow.table_id == table.id)
                .order_by(BulkTableRow.position, BulkTableRow.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    row_ids = [r.id for r in rows]
    cells = []
    if row_ids:
        cells = (
            (
                await db.execute(
                    select(BulkTableCell).where(BulkTableCell.row_id.in_(row_ids))
                )
            )
            .scalars()
            .all()
        )
    return TableRead.model_validate(
        {
            "id": table.id,
            "name": table.name,
            "description": table.description,
            "folder_id": table.folder_id,
            "created_by_id": table.created_by_id,
            "created_by_name": await _resolve_creator_name(db, table.created_by_id),
            "created_at": table.created_at,
            "updated_at": table.updated_at,
            "autotool_enabled": table.autotool_enabled,
            "autotool_token": table.autotool_token,
            "columns": [ColumnRead.model_validate(c) for c in columns],
            "rows": [RowRead.model_validate(r) for r in rows],
            "cells": [
                {
                    "id": c.id,
                    "row_id": c.row_id,
                    "column_id": c.column_id,
                    "value": c.value,
                    "status": c.status,
                    "error": c.error,
                    "model_used": c.model_used,
                    "generated_at": c.generated_at,
                    "updated_at": c.updated_at,
                    "translations": c.translations,
                }
                for c in cells
            ],
            "total_row_count": int(total),
        }
    )


async def _bump_table_updated(db: AsyncSession, table_id: int) -> None:
    """Force the table's updated_at to refresh on dependent writes.

    The previous implementation was ``t.name = t.name`` — but assigning the
    same value doesn't dirty the attribute, so SQLAlchemy never issued an
    UPDATE and the ``onupdate=func.now()`` server hook never fired. Library
    list ordering by updated_at was silently stale. Use a direct UPDATE so
    the column moves regardless of the in-session attribute state.
    """
    await db.execute(
        update(BulkTable)
        .where(BulkTable.id == table_id)
        .values(updated_at=func.now())
    )


# ---------- folders ----------
#
# Folders are global organizational containers (no per-user visibility) — same
# pattern as prompt categories. The actual table-list visibility is still gated
# by `_can_access`, so a content_generator looking at a folder simply won't see
# foreign tables in it.

@router.get("/folders", response_model=list[FolderRead])
async def list_folders(
    with_counts: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[FolderRead]:
    rows = list(
        (
            await db.execute(
                select(BulkTableFolder).order_by(BulkTableFolder.name)
            )
        ).scalars().all()
    )
    if not with_counts:
        return [FolderRead.model_validate(f) for f in rows]
    counts = dict(
        (
            await db.execute(
                select(BulkTable.folder_id, func.count(BulkTable.id))
                .where(
                    BulkTable.folder_id.is_not(None),
                    BulkTable.deleted_at.is_(None),
                )
                .group_by(BulkTable.folder_id)
            )
        ).all()
    )
    out: list[FolderRead] = []
    for f in rows:
        fr = FolderRead.model_validate(f)
        fr.table_count = int(counts.get(f.id, 0))
        out.append(fr)
    return out


@router.post(
    "/folders", response_model=FolderRead, status_code=status.HTTP_201_CREATED
)
async def create_folder(
    payload: FolderCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FolderRead:
    f = BulkTableFolder(name=payload.name.strip(), created_by_id=actor.id)
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return FolderRead.model_validate(f)


@router.patch("/folders/{folder_id}", response_model=FolderRead)
async def rename_folder(
    folder_id: int,
    payload: FolderUpdate,
    db: AsyncSession = Depends(get_db),
) -> FolderRead:
    f = await db.get(BulkTableFolder, folder_id)
    if f is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    f.name = payload.name.strip()
    await db.commit()
    await db.refresh(f)
    return FolderRead.model_validate(f)


@router.delete(
    "/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_folder(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    f = await db.get(BulkTableFolder, folder_id)
    if f is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    # Delete only when empty (FK is ON DELETE RESTRICT). Surface a clean error
    # so the user knows to move tables out first.
    # Trashed tables don't count — the folder is "empty" if every remaining
    # table in it has been trashed. The trashed tables still carry the
    # folder_id, which is fine: restore puts them back into the same folder
    # (creating the folder again if it was deleted in the meantime would be a
    # separate problem; today we just SET NULL on restore if the folder is
    # gone, see _normalize_folder_on_restore).
    in_use = (
        await db.execute(
            select(func.count(BulkTable.id)).where(
                BulkTable.folder_id == folder_id,
                BulkTable.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    if int(in_use) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Folder has {int(in_use)} table(s) in it. "
                "Move them out before deleting."
            ),
        )
    await db.delete(f)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- tables ----------

@router.get("/tables", response_model=TableListResponse)
async def list_tables(
    folder_id: int | None = Query(
        default=None,
        description=(
            "Filter by folder. Omit for 'all'; use 0 for 'uncategorized' "
            "(tables with no folder)."
        ),
    ),
    q: str | None = Query(default=None, description="Case-insensitive name search"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableListResponse:
    role = _role_name(actor)
    sees_all = role in {"admin", "manager"}

    base = (
        select(BulkTable)
        .where(BulkTable.deleted_at.is_(None))
        .order_by(BulkTable.updated_at.desc())
    )
    count_stmt = select(func.count(BulkTable.id)).where(
        BulkTable.deleted_at.is_(None)
    )
    if not sees_all:
        base = base.where(BulkTable.created_by_id == actor.id)
        count_stmt = count_stmt.where(BulkTable.created_by_id == actor.id)

    if folder_id is not None:
        if folder_id == 0:
            base = base.where(BulkTable.folder_id.is_(None))
            count_stmt = count_stmt.where(BulkTable.folder_id.is_(None))
        else:
            base = base.where(BulkTable.folder_id == folder_id)
            count_stmt = count_stmt.where(BulkTable.folder_id == folder_id)

    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.where(or_(BulkTable.name.ilike(like)))
        count_stmt = count_stmt.where(or_(BulkTable.name.ilike(like)))

    total = int((await db.execute(count_stmt)).scalar_one())

    base = base.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(base)).scalars().all()

    # Resolve creator names in one query
    creator_ids = {t.created_by_id for t in rows if t.created_by_id is not None}
    creator_names: dict[int, str] = {}
    if creator_ids:
        creator_rows = (
            await db.execute(
                select(User.id, User.full_name, User.email).where(
                    User.id.in_(creator_ids)
                )
            )
        ).all()
        for uid, full_name, email in creator_rows:
            creator_names[int(uid)] = (full_name or email) or ""

    # Compute counts in one go
    counts = dict(
        (
            await db.execute(
                select(BulkTableColumn.table_id, func.count(BulkTableColumn.id))
                .where(BulkTableColumn.table_id.in_([r.id for r in rows] or [0]))
                .group_by(BulkTableColumn.table_id)
            )
        ).all()
    )
    row_counts = dict(
        (
            await db.execute(
                select(BulkTableRow.table_id, func.count(BulkTableRow.id))
                .where(BulkTableRow.table_id.in_([r.id for r in rows] or [0]))
                .group_by(BulkTableRow.table_id)
            )
        ).all()
    )
    items = [
        TableListItem(
            id=t.id,
            name=t.name,
            description=t.description,
            folder_id=t.folder_id,
            created_by_id=t.created_by_id,
            created_by_name=creator_names.get(t.created_by_id) if t.created_by_id else None,
            created_at=t.created_at,
            updated_at=t.updated_at,
            column_count=int(counts.get(t.id, 0)),
            row_count=int(row_counts.get(t.id, 0)),
        )
        for t in rows
    ]
    return TableListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/tables", response_model=TableRead, status_code=status.HTTP_201_CREATED)
async def create_table(
    payload: TableCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRead:
    if payload.folder_id is not None:
        await _verify_folder(db, payload.folder_id)
    t = BulkTable(
        name=payload.name.strip(),
        description=payload.description,
        folder_id=payload.folder_id,
        created_by_id=actor.id,
    )
    db.add(t)
    await db.flush()  # get t.id

    cols_to_add = (
        payload.initial_columns if payload.initial_columns else ["Column 1", "Column 2"]
    )
    for i, name in enumerate(cols_to_add):
        db.add(BulkTableColumn(table_id=t.id, position=i, name=name, kind="input"))

    for i in range(payload.initial_row_count):
        db.add(BulkTableRow(table_id=t.id, position=i))

    await db.commit()

    # Reload with columns + rows
    fresh = await _get_owned_table_or_404(db, t.id, actor, full=True)
    return await _table_to_read(db, fresh)


@router.get("/tables/{table_id}", response_model=TableRead)
async def get_table(
    table_id: int,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=1000),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRead:
    """Fetch a bulk table.

    Without `page`/`page_size`, returns the full table (all rows + cells) —
    the legacy shape relied on by duplicate, CSV import and trash preview.
    With both set, returns just that page of rows and their cells plus
    `total_row_count`, so large tables don't ship every cell on open.
    """
    if page is not None and page_size is not None:
        t = await _get_table_or_404(db, table_id, actor, level="read")
        return await _table_to_read_paginated(db, t, page, page_size)
    t = await _get_table_or_404(db, table_id, actor, level="read", full=True)
    return await _table_to_read(db, t)


@router.patch("/tables/{table_id}", response_model=TableListItem)
async def update_table(
    table_id: int,
    payload: TableUpdate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableListItem:
    t = await _get_owned_table_or_404(db, table_id, actor)
    data = payload.model_dump(exclude_unset=True)
    if "folder_id" in data and data["folder_id"] is not None:
        await _verify_folder(db, data["folder_id"])
    for k, v in data.items():
        setattr(t, k, v)
    await db.commit()
    await db.refresh(t)
    return TableListItem(
        id=t.id,
        name=t.name,
        description=t.description,
        folder_id=t.folder_id,
        created_by_id=t.created_by_id,
        created_by_name=await _resolve_creator_name(db, t.created_by_id),
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.post("/tables/bulk-move", response_model=dict)
async def bulk_move_tables(
    payload: TableBulkMove,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Move N active tables to a folder (or out of any folder).

    Used by the "Move to folder…" bulk action on /library. Mirrors
    ``bulk_move_domains`` so the frontend's MoveToFolderModal can be
    reused as-is.

    Trashed tables are silently skipped — only active rows can be
    moved (a trashed table shouldn't suddenly hop into a folder behind
    the user's back). Non-owners (when actor isn't admin/manager) are
    also silently skipped via the same ownership filter used by the
    list endpoints.

    Body: ``{"table_ids": [int, ...], "folder_id": int | null}``.
    Returns ``{"moved": <count>}`` so the UI can confirm.
    """
    if payload.folder_id is not None:
        await _verify_folder(db, payload.folder_id)

    role = _role_name(actor)
    sees_all = role in {"admin", "manager"}

    stmt = select(BulkTable).where(
        BulkTable.id.in_(payload.table_ids),
        BulkTable.deleted_at.is_(None),
    )
    if not sees_all:
        stmt = stmt.where(BulkTable.created_by_id == actor.id)

    rows = (await db.execute(stmt)).scalars().all()
    for t in rows:
        t.folder_id = payload.folder_id
    await db.commit()
    return {"moved": len(rows)}


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Move a table to trash (soft-delete).

    Sets ``deleted_at = now()`` so the table disappears from /library and
    from all editor / generation / publish routes — but the data stays
    intact. Restorable from /library/trash. Auto-emptied by the cleanup
    Celery task after ``bulk_table_trash_retention_days`` (default 50,
    admin-configurable; 0 disables auto-empty).

    Refuses (409) when an in-flight bulk publish run is using this table:
    queued / running / paused. Cancel the run first.
    """
    t = await _get_table_or_404(db, table_id, actor, level="delete")
    blocking_run_id = await _has_active_publish_run(db, t.id)
    if blocking_run_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot trash this table while bulk publish run "
                f"#{blocking_run_id} is in flight. Pause/cancel the run "
                f"first (see /publish/runs/{blocking_run_id})."
            ),
        )
    t.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ---------- trash ----------
#
# The trash surface is parallel to the tables surface: list, preview, and
# (per-id + bulk) restore/permanent-delete. Trashed rows are hidden from
# every other endpoint. Visibility mirrors the active list: content_generator
# sees own; manager/admin see all.


@router.get("/trash", response_model=TableListResponse)
async def list_trashed_tables(
    q: str | None = Query(default=None, description="Case-insensitive name search"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableListResponse:
    role = _role_name(actor)
    sees_all = role in {"admin", "manager"}

    base = (
        select(BulkTable)
        .where(BulkTable.deleted_at.is_not(None))
        .order_by(BulkTable.deleted_at.desc())
    )
    count_stmt = select(func.count(BulkTable.id)).where(
        BulkTable.deleted_at.is_not(None)
    )
    if not sees_all:
        base = base.where(BulkTable.created_by_id == actor.id)
        count_stmt = count_stmt.where(BulkTable.created_by_id == actor.id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.where(BulkTable.name.ilike(like))
        count_stmt = count_stmt.where(BulkTable.name.ilike(like))

    total = int((await db.execute(count_stmt)).scalar_one())
    base = base.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(base)).scalars().all()

    creator_ids = {t.created_by_id for t in rows if t.created_by_id is not None}
    creator_names: dict[int, str] = {}
    if creator_ids:
        creator_rows = (
            await db.execute(
                select(User.id, User.full_name, User.email).where(
                    User.id.in_(creator_ids)
                )
            )
        ).all()
        for uid, full_name, email in creator_rows:
            creator_names[int(uid)] = (full_name or email) or ""

    ids_or_zero = [r.id for r in rows] or [0]
    col_counts = dict(
        (
            await db.execute(
                select(BulkTableColumn.table_id, func.count(BulkTableColumn.id))
                .where(BulkTableColumn.table_id.in_(ids_or_zero))
                .group_by(BulkTableColumn.table_id)
            )
        ).all()
    )
    row_counts = dict(
        (
            await db.execute(
                select(BulkTableRow.table_id, func.count(BulkTableRow.id))
                .where(BulkTableRow.table_id.in_(ids_or_zero))
                .group_by(BulkTableRow.table_id)
            )
        ).all()
    )
    items = [
        TableListItem(
            id=t.id,
            name=t.name,
            description=t.description,
            folder_id=t.folder_id,
            created_by_id=t.created_by_id,
            created_by_name=creator_names.get(t.created_by_id) if t.created_by_id else None,
            created_at=t.created_at,
            updated_at=t.updated_at,
            column_count=int(col_counts.get(t.id, 0)),
            row_count=int(row_counts.get(t.id, 0)),
            deleted_at=t.deleted_at,
        )
        for t in rows
    ]
    return TableListResponse(items=items, total=total, page=page, page_size=page_size)


_TRASH_RETENTION_KEY = "bulk_table_trash_retention_days"
_TRASH_RETENTION_DEFAULT = 50
_TRASH_RETENTION_MAX = 3650  # ~10 years; anything above this is a typo.


@router.get("/trash/retention", response_model=dict)
async def get_trash_retention(
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role("admin", "manager")),
) -> dict:
    row = (
        await db.execute(
            select(AppSetting.value).where(AppSetting.key == _TRASH_RETENTION_KEY)
        )
    ).scalar_one_or_none()
    try:
        days = max(0, int(row)) if row is not None else _TRASH_RETENTION_DEFAULT
    except (TypeError, ValueError):
        days = _TRASH_RETENTION_DEFAULT
    return {"days": days, "default": _TRASH_RETENTION_DEFAULT, "max": _TRASH_RETENTION_MAX}


@router.put("/trash/retention", response_model=dict)
async def set_trash_retention(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> dict:
    raw = payload.get("days")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`days` must be an integer (0 disables auto-empty).",
        )
    if days < 0 or days > _TRASH_RETENTION_MAX:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"`days` must be between 0 and {_TRASH_RETENTION_MAX}.",
        )
    existing = await db.get(AppSetting, _TRASH_RETENTION_KEY)
    if existing is None:
        db.add(AppSetting(key=_TRASH_RETENTION_KEY, value=days))
    else:
        existing.value = days
    await db.commit()
    # In-process app_settings cache invalidate. The trash cleanup task reads
    # via direct query (no cache), but other future readers might use the
    # cache — invalidating here keeps it consistent.
    try:
        from app.services.app_settings_cache import invalidate
        invalidate(_TRASH_RETENTION_KEY)
    except Exception:
        pass
    return {"days": days, "default": _TRASH_RETENTION_DEFAULT, "max": _TRASH_RETENTION_MAX}


@router.get("/trash/count", response_model=dict)
async def trash_count(
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cheap count for the 'Trash (N)' badge in the library toolbar."""
    role = _role_name(actor)
    sees_all = role in {"admin", "manager"}
    stmt = select(func.count(BulkTable.id)).where(BulkTable.deleted_at.is_not(None))
    if not sees_all:
        stmt = stmt.where(BulkTable.created_by_id == actor.id)
    n = int((await db.execute(stmt)).scalar_one())
    return {"count": n}


@router.get("/trash/{table_id}", response_model=TableRead)
async def preview_trashed_table(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRead:
    """Read-only preview of a trashed table.

    Returns the same shape as ``GET /library/tables/{id}`` so the frontend
    can render a read-only version of the grid. All write endpoints
    (cells, columns, rows, generation, publish) refuse to find this row
    because they use ``_get_table_or_404`` with ``include_trashed=False``.
    """
    t = await _get_trashed_table_or_404(db, table_id, actor, level="read", full=True)
    out = await _table_to_read(db, t)
    out.deleted_at = t.deleted_at
    return out


@router.post("/tables/{table_id}/restore", response_model=TableListItem)
async def restore_table(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableListItem:
    """Move a trashed table back to the active library.

    Clears `deleted_at`. If the original folder has been deleted in the
    meantime, the table is restored uncategorized (`folder_id=NULL`) so
    the FK doesn't break — we don't auto-recreate the folder.
    """
    t = await _get_trashed_table_or_404(db, table_id, actor, level="delete")
    if t.folder_id is not None:
        # Folder may have been deleted while this table was in trash.
        folder = await db.get(BulkTableFolder, t.folder_id)
        if folder is None:
            t.folder_id = None
    t.deleted_at = None
    # Bump updated_at so it sorts to the top of the library list as
    # "recently changed".
    await _bump_table_updated(db, t.id)
    await db.commit()
    await db.refresh(t)
    return TableListItem(
        id=t.id,
        name=t.name,
        description=t.description,
        folder_id=t.folder_id,
        created_by_id=t.created_by_id,
        created_by_name=await _resolve_creator_name(db, t.created_by_id),
        created_at=t.created_at,
        updated_at=t.updated_at,
        deleted_at=None,
    )


@router.delete(
    "/tables/{table_id}/permanent", status_code=status.HTTP_204_NO_CONTENT
)
async def permanently_delete_table(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Hard-delete a trashed table.

    Only callable from the trash surface (`deleted_at IS NOT NULL`). The
    cascades on `bulk_table_columns`, `bulk_table_rows`, `bulk_table_cells`,
    `bulk_publish_runs` (table_id FK ON DELETE CASCADE) and
    `bulk_table_publish_mappings` (table_id FK ON DELETE CASCADE) clean up
    everything that pointed at this table.
    """
    t = await _get_trashed_table_or_404(db, table_id, actor, level="delete")
    await db.delete(t)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/trash", status_code=status.HTTP_200_OK)
async def empty_trash(
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete every trashed table the actor can see.

    Visibility mirrors the trash list: content_generator empties only their
    own; manager / admin empty everyone's.
    """
    role = _role_name(actor)
    sees_all = role in {"admin", "manager"}
    stmt = select(BulkTable).where(BulkTable.deleted_at.is_not(None))
    if not sees_all:
        stmt = stmt.where(BulkTable.created_by_id == actor.id)
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return {"deleted": 0}
    for t in rows:
        await db.delete(t)
    await db.commit()
    return {"deleted": len(rows)}


@router.post("/trash/bulk-restore", response_model=dict)
async def bulk_restore(
    payload: TrashBulkIds,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Restore many trashed tables in one call.

    Tables the actor can't access (or that aren't actually trashed) are
    silently skipped so a half-stale UI never 404s the whole batch.
    """
    rows = (
        await db.execute(
            select(BulkTable).where(
                BulkTable.id.in_(payload.ids),
                BulkTable.deleted_at.is_not(None),
            )
        )
    ).scalars().all()
    restored = 0
    for t in rows:
        if not _can_access(actor, t, "delete"):
            continue
        if t.folder_id is not None:
            folder = await db.get(BulkTableFolder, t.folder_id)
            if folder is None:
                t.folder_id = None
        t.deleted_at = None
        await _bump_table_updated(db, t.id)
        restored += 1
    await db.commit()
    return {"restored": restored}


@router.delete("/trash/bulk", response_model=dict)
async def bulk_permanent_delete(
    payload: TrashBulkIds,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete many trashed tables in one call."""
    rows = (
        await db.execute(
            select(BulkTable).where(
                BulkTable.id.in_(payload.ids),
                BulkTable.deleted_at.is_not(None),
            )
        )
    ).scalars().all()
    deleted = 0
    for t in rows:
        if not _can_access(actor, t, "delete"):
            continue
        await db.delete(t)
        deleted += 1
    await db.commit()
    return {"deleted": deleted}


@router.post("/tables/{table_id}/duplicate", response_model=TableRead, status_code=status.HTTP_201_CREATED)
async def duplicate_table(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRead:
    src = await _get_table_or_404(db, table_id, actor, level="read", full=True)

    # New table (the duplicate is owned by the actor, not the source's owner;
    # but it stays in the same folder for organizational continuity).
    dup = BulkTable(
        name=f"{src.name} (copy)",
        description=src.description,
        folder_id=src.folder_id,
        created_by_id=actor.id,
    )
    db.add(dup)
    await db.flush()

    # Map source IDs -> new IDs so cells can reference them.
    col_id_map: dict[int, int] = {}
    for c in src.columns:
        new_col = BulkTableColumn(
            table_id=dup.id,
            position=c.position,
            name=c.name,
            kind=c.kind,
            prompt_id=c.prompt_id,
            prompt_version_number=c.prompt_version_number,
            variable_map=dict(c.variable_map) if c.variable_map else {},
        )
        db.add(new_col)
        await db.flush()
        col_id_map[c.id] = new_col.id

    row_id_map: dict[int, int] = {}
    for r in src.rows:
        new_row = BulkTableRow(table_id=dup.id, position=r.position)
        db.add(new_row)
        await db.flush()
        row_id_map[r.id] = new_row.id

    # Copy cells but reset AI-status to 'manual' (or 'empty' if empty)
    src_cells = (
        (
            await db.execute(
                select(BulkTableCell).where(
                    BulkTableCell.row_id.in_([r.id for r in src.rows] or [0])
                )
            )
        )
        .scalars()
        .all()
    )
    for c in src_cells:
        new_status = "manual" if c.value not in (None, "") else "empty"
        db.add(
            BulkTableCell(
                row_id=row_id_map[c.row_id],
                column_id=col_id_map[c.column_id],
                value=c.value,
                status=new_status,
                error=None,
                model_used=None,
                generated_at=None,
            )
        )

    await db.commit()

    # Re-fetch the freshly duplicated table the actor now owns.
    fresh = await _get_table_or_404(db, dup.id, actor, level="read", full=True)
    return await _table_to_read(db, fresh)


# ---------- columns ----------

@router.post(
    "/tables/{table_id}/columns",
    response_model=ColumnRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_column(
    table_id: int,
    payload: ColumnCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ColumnRead:
    t = await _get_owned_table_or_404(db, table_id, actor)
    if payload.position is None:
        max_pos = (
            await db.execute(
                select(func.coalesce(func.max(BulkTableColumn.position), -1)).where(
                    BulkTableColumn.table_id == t.id
                )
            )
        ).scalar_one()
        position = int(max_pos) + 1
    else:
        position = payload.position
    col = BulkTableColumn(
        table_id=t.id,
        position=position,
        name=payload.name.strip(),
        kind=payload.kind,
        prompt_id=payload.prompt_id,
        prompt_version_number=payload.prompt_version_number,
        variable_map=payload.variable_map,
    )
    db.add(col)
    await _bump_table_updated(db, t.id)
    await db.commit()
    await db.refresh(col)
    return ColumnRead.model_validate(col)


@router.patch("/tables/{table_id}/columns/{column_id}", response_model=ColumnRead)
async def update_column(
    table_id: int,
    column_id: int,
    payload: ColumnUpdate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ColumnRead:
    await _get_owned_table_or_404(db, table_id, actor)
    col = (
        await db.execute(
            select(BulkTableColumn).where(
                BulkTableColumn.id == column_id, BulkTableColumn.table_id == table_id
            )
        )
    ).scalar_one_or_none()
    if col is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(col, k, v)
    await _bump_table_updated(db, table_id)
    await db.commit()
    await db.refresh(col)
    return ColumnRead.model_validate(col)


@router.delete(
    "/tables/{table_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_column(
    table_id: int,
    column_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_owned_table_or_404(db, table_id, actor)
    col = (
        await db.execute(
            select(BulkTableColumn).where(
                BulkTableColumn.id == column_id, BulkTableColumn.table_id == table_id
            )
        )
    ).scalar_one_or_none()
    if col is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    await db.delete(col)
    await _bump_table_updated(db, table_id)
    await db.commit()


# ---------- rows ----------

@router.post(
    "/tables/{table_id}/rows", response_model=RowRead, status_code=status.HTTP_201_CREATED
)
async def add_row(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RowRead:
    await _get_owned_table_or_404(db, table_id, actor)
    max_pos = (
        await db.execute(
            select(func.coalesce(func.max(BulkTableRow.position), -1)).where(
                BulkTableRow.table_id == table_id
            )
        )
    ).scalar_one()
    row = BulkTableRow(table_id=table_id, position=int(max_pos) + 1)
    db.add(row)
    await _bump_table_updated(db, table_id)
    await db.commit()
    await db.refresh(row)
    return RowRead.model_validate(row)


@router.delete("/tables/{table_id}/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(
    table_id: int,
    row_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_owned_table_or_404(db, table_id, actor)
    row = (
        await db.execute(
            select(BulkTableRow).where(
                BulkTableRow.id == row_id, BulkTableRow.table_id == table_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    await db.delete(row)
    await _bump_table_updated(db, table_id)
    await db.commit()


# ---------- cells ----------

async def _upsert_one_cell(
    db: AsyncSession, table_id: int, payload: CellUpsert
) -> BulkTableCell:
    # Verify the row + column belong to the requested table to prevent cross-table writes.
    row = (
        await db.execute(
            select(BulkTableRow).where(
                BulkTableRow.id == payload.row_id, BulkTableRow.table_id == table_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad row_id")
    col = (
        await db.execute(
            select(BulkTableColumn).where(
                BulkTableColumn.id == payload.column_id,
                BulkTableColumn.table_id == table_id,
            )
        )
    ).scalar_one_or_none()
    if col is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad column_id")

    cell = (
        await db.execute(
            select(BulkTableCell).where(
                BulkTableCell.row_id == payload.row_id,
                BulkTableCell.column_id == payload.column_id,
            )
        )
    ).scalar_one_or_none()

    new_status = payload.status or _default_status_for(payload.value)

    if cell is None:
        cell = BulkTableCell(
            row_id=payload.row_id,
            column_id=payload.column_id,
            value=payload.value,
            status=new_status,
        )
        db.add(cell)
    else:
        # Editing the source value invalidates any cached translations —
        # otherwise the side-by-side translation panel would show stale
        # output that no longer matches the original.
        if cell.value != payload.value and cell.translations is not None:
            cell.translations = None
        cell.value = payload.value
        cell.status = new_status

    return cell


@router.put("/tables/{table_id}/cells", response_model=list[dict])
async def upsert_cells(
    table_id: int,
    payload: CellsBatchUpsert,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Batch upsert. Used by the auto-save debouncer in the editor."""
    await _get_owned_table_or_404(db, table_id, actor)
    out_cells: list[BulkTableCell] = []
    try:
        for c in payload.cells:
            cell = await _upsert_one_cell(db, table_id, c)
            out_cells.append(cell)
        await _bump_table_updated(db, table_id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cell write conflict, retry"
        )
    out: list[dict] = []
    for c in out_cells:
        await db.refresh(c)
        out.append(
            {
                "id": c.id,
                "row_id": c.row_id,
                "column_id": c.column_id,
                "value": c.value,
                "status": c.status,
                "updated_at": c.updated_at.isoformat(),
            }
        )
    return out


@router.post("/tables/{table_id}/clear-values", response_model=ClearValuesResponse)
async def clear_values(
    table_id: int,
    payload: ClearValuesRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClearValuesResponse:
    """Wipe cell values in bulk, server-side.

    Pass ``all=True`` to clear every row, or ``row_ids`` to clear specific
    rows. Each affected cell is reset to an empty/manual-cleared state
    (value NULL, status 'empty', error cleared, translations dropped). The
    editor's 'Clear values' uses this so a selection that spans pages (the
    select-all-N case) clears completely — the browser no longer holds every
    cell to build the write batch itself.
    """
    await _get_owned_table_or_404(db, table_id, actor, level="write")

    # Target the table's rows (optionally a subset). Scope cells via a row
    # subquery so a stray row_id from another table can't be touched.
    row_subq = select(BulkTableRow.id).where(BulkTableRow.table_id == table_id)
    if not payload.all:
        ids = payload.row_ids or []
        if not ids:
            return ClearValuesResponse(cleared=0)
        row_subq = row_subq.where(BulkTableRow.id.in_(ids))

    stmt = (
        update(BulkTableCell)
        .where(BulkTableCell.row_id.in_(row_subq))
        .values(value=None, status="empty", error=None, translations=None)
    )
    result = await db.execute(stmt)
    await _bump_table_updated(db, table_id)
    await db.commit()
    return ClearValuesResponse(cleared=int(result.rowcount or 0))


@router.get("/tables/{table_id}/column-values", response_model=ColumnValuesResponse)
async def column_values(
    table_id: int,
    column_ids: str = Query(default=""),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ColumnValuesResponse:
    """Lightweight per-column values for the bulk-publish previews.

    Returns the full ordered row list (id + ordinal position) plus the values
    of ONLY the requested columns (``column_ids`` = comma-separated ids).
    Lets the publish modal compute its 'Will publish N' / per-domain /
    language-sync previews and resolve ordinal ranges without loading the
    heavy output cells of every row.
    """
    await _get_table_or_404(db, table_id, actor, level="read")

    wanted: list[int] = []
    for part in column_ids.split(","):
        part = part.strip()
        if part:
            try:
                wanted.append(int(part))
            except ValueError:
                continue
    # Keep only columns that actually belong to this table.
    valid_ids: set[int] = set()
    if wanted:
        valid_ids = set(
            (
                await db.execute(
                    select(BulkTableColumn.id).where(
                        BulkTableColumn.table_id == table_id,
                        BulkTableColumn.id.in_(wanted),
                    )
                )
            )
            .scalars()
            .all()
        )

    rows = (
        (
            await db.execute(
                select(BulkTableRow.id, BulkTableRow.position)
                .where(BulkTableRow.table_id == table_id)
                .order_by(BulkTableRow.position, BulkTableRow.id)
            )
        )
        .all()
    )

    values: dict[int, dict[int, str]] = {}
    if valid_ids:
        cell_rows = (
            await db.execute(
                select(
                    BulkTableCell.row_id,
                    BulkTableCell.column_id,
                    BulkTableCell.value,
                )
                .join(BulkTableRow, BulkTableRow.id == BulkTableCell.row_id)
                .where(
                    BulkTableRow.table_id == table_id,
                    BulkTableCell.column_id.in_(valid_ids),
                )
            )
        ).all()
        for rid, cid, val in cell_rows:
            if val is None:
                continue
            values.setdefault(int(rid), {})[int(cid)] = val

    return ColumnValuesResponse(
        rows=[{"id": int(rid), "position": int(pos)} for rid, pos in rows],
        values=values,
    )


# ---------- Cell translation ----------

@router.post(
    "/tables/{table_id}/cells/{row_id}/{column_id}/translate",
    response_model=dict,
)
async def translate_cell(
    table_id: int,
    row_id: int,
    column_id: int,
    payload: dict,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run the configured brain `translate` prompt against an output cell.

    Body: ``{"target_language": "ru"}``. Target falls back to the brain
    default when empty. Result is memoized on
    ``bulk_table_cells.translations[<lang>]`` so reopens hit the cache.
    Cached entries for a cell are invalidated whenever the underlying
    value changes (upsert path + bulk-generation worker).
    """
    from app.providers.base import ProviderError as _ProviderError
    from app.providers.registry import ProviderNotConfigured as _ProviderNotConfigured
    from app.services.brain import (
        cache_lookup as _cache_lookup,
        make_translation_entry as _make_entry,
        resolve_target_language as _resolve_lang,
        translate_text as _translate_text,
    )

    await _get_table_or_404(db, table_id, actor, level="read")

    cell = (
        await db.execute(
            select(BulkTableCell)
            .join(BulkTableColumn, BulkTableColumn.id == BulkTableCell.column_id)
            .where(
                BulkTableCell.row_id == row_id,
                BulkTableCell.column_id == column_id,
                BulkTableColumn.table_id == table_id,
            )
        )
    ).scalar_one_or_none()
    if cell is None or not (cell.value and cell.value.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cell has no content to translate.",
        )

    requested = await _resolve_lang(db, payload.get("target_language"))

    # `force=true` lets the Re-translate button bypass the memoization —
    # the user explicitly asked for a fresh LLM call (typically because
    # the previous output was off and they want another shot).
    force = bool(payload.get("force"))

    # Cache hit — return what's already stored without an LLM call.
    if not force:
        cached = _cache_lookup(cell.translations, requested)
        if cached is not None:
            return {
                "target_language": requested,
                "cached": True,
                **cached,
            }

    try:
        text, code, model = await _translate_text(
            db, source_text=cell.value, target_language=requested
        )
    except _ProviderNotConfigured as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except _ProviderError as e:
        from app.services.error_log import log_error

        await log_error(
            db,
            source="api",
            category="provider_error",
            message=str(e),
            user_id=actor.id,
            status_code=getattr(e, "status_code", None),
            context={
                "endpoint": "/library/.../translate",
                "table_id": table_id,
                "row_id": row_id,
                "column_id": column_id,
                "target_language": requested,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )

    entry = _make_entry(text=text, provider_code=code, model=model)
    # JSONB mutation: copy + reassign so SQLAlchemy detects the change.
    next_translations = dict(cell.translations or {})
    next_translations[requested] = entry
    cell.translations = next_translations
    await db.commit()

    # Track-only spend log — translate calls show up under the actor in
    # /users so an admin can see how much the team is leaning on this.
    from app.services.usage import record_usage

    await record_usage(
        db,
        user_id=actor.id,
        provider_code=code,
        model=model,
        prompt_tokens=None,  # translate path doesn't surface usage today;
        completion_tokens=None,  # the provider response is text-only.
        source="brain_translate",
        source_ref={
            "table_id": table_id,
            "row_id": row_id,
            "column_id": column_id,
            "target_language": requested,
        },
    )

    return {
        "target_language": requested,
        "cached": False,
        **entry,
    }


# ---------- CSV ----------

@router.post(
    "/tables/import-csv", response_model=TableRead, status_code=status.HTTP_201_CREATED
)
async def import_csv(
    payload: CsvImportRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRead:
    reader = csv.reader(io.StringIO(payload.csv_text), delimiter=payload.delimiter)
    rows = [r for r in reader]
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV is empty")

    if payload.has_header:
        headers = [h.strip() or f"Column {i + 1}" for i, h in enumerate(rows[0])]
        data_rows = rows[1:]
    else:
        col_count = max(len(r) for r in rows)
        headers = [f"Column {i + 1}" for i in range(col_count)]
        data_rows = rows

    t = BulkTable(name=payload.name.strip(), created_by_id=actor.id)
    db.add(t)
    await db.flush()

    column_objs: list[BulkTableColumn] = []
    for i, h in enumerate(headers):
        col = BulkTableColumn(table_id=t.id, position=i, name=h, kind="input")
        db.add(col)
        column_objs.append(col)
    await db.flush()

    for ri, row_values in enumerate(data_rows):
        row_obj = BulkTableRow(table_id=t.id, position=ri)
        db.add(row_obj)
        await db.flush()
        for ci, val in enumerate(row_values):
            if ci >= len(column_objs):
                break  # ignore extra fields
            value = (val or "").strip()
            if value == "":
                continue
            db.add(
                BulkTableCell(
                    row_id=row_obj.id,
                    column_id=column_objs[ci].id,
                    value=value,
                    status="manual",
                )
            )

    await db.commit()
    fresh = await _get_owned_table_or_404(db, t.id, actor, full=True)
    return await _table_to_read(db, fresh)


# ---------- AI generation ----------


async def _resolve_generation_columns(
    db: AsyncSession, table_id: int, column_ids: list[int] | None
) -> list[BulkTableColumn]:
    """Output columns with a prompt assigned, optionally scoped to ``column_ids``."""
    col_q = select(BulkTableColumn).where(
        BulkTableColumn.table_id == table_id,
        BulkTableColumn.kind == "output",
        BulkTableColumn.prompt_id.is_not(None),
    )
    if column_ids:
        col_q = col_q.where(BulkTableColumn.id.in_(column_ids))
    return list((await db.execute(col_q)).scalars().all())


async def _resolve_generation_rows(
    db: AsyncSession, table_id: int, payload: GenerateRequest
) -> list[BulkTableRow]:
    """Target rows for a generation request.

    Precedence: explicit ``row_ids`` → ordinal ``row_range`` → all rows. The
    range is 1-based and inclusive over the position-ordered list, matching
    the grid's visible '#' numbers.
    """
    row_q = (
        select(BulkTableRow)
        .where(BulkTableRow.table_id == table_id)
        .order_by(BulkTableRow.position, BulkTableRow.id)
    )
    if payload.row_ids:
        row_q = row_q.where(BulkTableRow.id.in_(payload.row_ids))
    elif payload.row_range is not None:
        start = payload.row_range.start
        end = payload.row_range.end
        limit = max(0, end - start + 1)
        row_q = row_q.offset(start - 1).limit(limit)
    return list((await db.execute(row_q)).scalars().all())


async def _resolve_generation_candidates(
    db: AsyncSession,
    table_id: int,
    cols: list[BulkTableColumn],
    rows: list[BulkTableRow],
    payload: GenerateRequest,
) -> tuple[list[tuple[int, int]], int]:
    """Compute the (row_id, column_id) cells to enqueue and how many are
    skipped by the mode filter. Shared by the enqueue and preview endpoints so
    the dry-run count always matches what enqueue actually does."""
    existing_cells = (
        (
            await db.execute(
                select(BulkTableCell).where(
                    BulkTableCell.row_id.in_([r.id for r in rows]),
                    BulkTableCell.column_id.in_([c.id for c in cols]),
                )
            )
        )
        .scalars()
        .all()
    )
    existing_lookup = {(c.row_id, c.column_id): c for c in existing_cells}

    effective_mode = "all" if payload.overwrite else payload.mode
    to_enqueue: list[tuple[int, int]] = []
    skipped = 0
    for row in rows:
        for col in cols:
            existing = existing_lookup.get((row.id, col.id))
            existing_status = existing.status if existing is not None else "empty"
            include = (
                effective_mode == "all"
                or (effective_mode == "failed" and existing_status == "failed")
                or (effective_mode == "empty" and existing_status != "generated")
            )
            if not include:
                skipped += 1
                continue
            to_enqueue.append((row.id, col.id))
    return to_enqueue, skipped


@router.post(
    "/tables/{table_id}/generate-preview", response_model=GeneratePreviewResponse
)
async def generate_preview(
    table_id: int,
    payload: GenerateRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GeneratePreviewResponse:
    """Dry-run: how many cells WOULD be enqueued vs skipped for this request.

    Replaces the editor's old client-side scan of every cell — the queue
    modal calls this on open / filter change so the 'Will generate N' count
    is correct without the browser holding the whole table."""
    await _get_table_or_404(db, table_id, actor, level="read")
    cols = await _resolve_generation_columns(db, table_id, payload.column_ids)
    if not cols:
        return GeneratePreviewResponse(will_generate=0, skipped=0)
    rows = await _resolve_generation_rows(db, table_id, payload)
    if not rows:
        return GeneratePreviewResponse(will_generate=0, skipped=0)
    to_enqueue, skipped = await _resolve_generation_candidates(
        db, table_id, cols, rows, payload
    )
    return GeneratePreviewResponse(will_generate=len(to_enqueue), skipped=skipped)


@router.post("/tables/{table_id}/generate", response_model=GenerateResponse)
async def enqueue_generation(
    table_id: int,
    payload: GenerateRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    """Mark cells 'generating' and enqueue one Celery task per cell."""
    await _get_owned_table_or_404(db, table_id, actor)

    # Queue-wide override validation: both or neither.
    if (payload.override_provider_code is None) != (payload.override_model is None):
        raise HTTPException(
            status_code=400,
            detail="override_provider_code and override_model must be set together",
        )

    # Resolve target columns (output columns with a prompt assigned).
    cols = await _resolve_generation_columns(db, table_id, payload.column_ids)

    if not cols:
        return GenerateResponse(
            enqueued_cell_ids=[], skipped=0,
            message=(
                "Nothing to do: no output columns with prompts. "
                "Configure a prompt on an output column first."
            ),
        )

    # Resolve target rows (row_ids → ordinal row_range → all).
    rows = await _resolve_generation_rows(db, table_id, payload)

    if not rows:
        return GenerateResponse(
            enqueued_cell_ids=[], skipped=0, message="No rows to generate."
        )

    # Compute the include set first; THEN do one bulk DB write; THEN enqueue.
    # The previous version was per-cell `_ensure_cell + UPDATE + COMMIT`, which
    # is roughly 3 round trips × N cells. For a 10k×5 table with all cells
    # included that was 150k round trips inside one HTTP request — minutes of
    # latency just for the bookkeeping. Bulk INSERT … ON CONFLICT … RETURNING
    # collapses it to a single statement. The candidate computation is shared
    # with /generate-preview so the dry-run count can't drift from reality.
    to_enqueue, skipped = await _resolve_generation_candidates(
        db, table_id, cols, rows, payload
    )

    effective_mode = "all" if payload.overwrite else payload.mode

    enqueued: list[int] = []
    run_id: int | None = None
    if to_enqueue:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        # Create the run BEFORE we mark cells, so we can stamp each
        # cell with its run_id in the same upsert. The seed status is
        # "running" — there's no "queued before workers see it" phase
        # to model, the Celery push is microseconds after the commit.
        run = BulkGenerationRun(
            table_id=table_id,
            status="running",
            total=len(to_enqueue),
            done=0,
            failed=0,
            skipped=0,
            created_by_id=actor.id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()  # populate run.id before child inserts
        run_id = run.id

        rows_payload = [
            {
                "row_id": rid,
                "column_id": cid,
                "status": "generating",
                "error": None,
                "generation_run_id": run_id,
            }
            for rid, cid in to_enqueue
        ]
        stmt = pg_insert(BulkTableCell).values(rows_payload)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_bulk_cells_row_column",
            set_={
                "status": "generating",
                "error": None,
                "generation_run_id": run_id,
            },
        ).returning(BulkTableCell.id)
        result = await db.execute(stmt)
        enqueued = [int(r[0]) for r in result.all()]
        await db.commit()

        # Enqueue Celery tasks AFTER commit so workers don't pick up cells
        # that aren't visible yet. .delay() is just a Redis push, so even a
        # tight loop of N enqueues is in the order of milliseconds for N=10k.
        # Override values are forwarded as kwargs (None when not set).
        for rid, cid in to_enqueue:
            generate_bulk_cell.delay(
                table_id,
                rid,
                cid,
                override_provider_code=payload.override_provider_code,
                override_model=payload.override_model,
                run_id=run_id,
            )

    mode_label = {"empty": "empty", "failed": "failed", "all": "all"}[effective_mode]
    msg = f"Enqueued {len(enqueued)} cell(s) (mode: {mode_label})."
    if skipped:
        msg += f" Skipped {skipped} cell(s) that didn't match the filter."
    return GenerateResponse(
        enqueued_cell_ids=enqueued, skipped=skipped, message=msg, run_id=run_id
    )


# ---------- Generation run lifecycle ----------

async def _get_gen_run_or_404(
    db: AsyncSession, run_id: int
) -> BulkGenerationRun:
    run = await db.get(BulkGenerationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return run


@router.get(
    "/tables/{table_id}/active-gen-run",
    response_model=BulkGenerationRunRead | None,
)
async def get_active_gen_run(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkGenerationRun | None:
    """Return the currently-active (queued/running) bulk generation run
    for the table, or None if none is active.

    The editor polls this every couple of seconds while a generation
    might be in flight. We deliberately ignore historical runs here —
    use ``GET /library/gen-runs/{id}`` for that.
    """
    await _get_table_or_404(db, table_id, actor, level="read")
    row = (
        await db.execute(
            select(BulkGenerationRun)
            .where(
                BulkGenerationRun.table_id == table_id,
                BulkGenerationRun.status.in_(["queued", "running"]),
            )
            .order_by(BulkGenerationRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


@router.get("/gen-runs/{run_id}", response_model=BulkGenerationRunDetail)
async def get_gen_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkGenerationRunDetail:
    """Full state for one generation run — counters, status, who
    started it, when. The detail page polls this every ~2s while the
    run is active, then stops on a terminal status."""
    run = await _get_gen_run_or_404(db, run_id)
    # Authorisation: any reader of the underlying table can see its
    # gen-runs. _get_table_or_404 throws if not allowed.
    await _get_table_or_404(db, run.table_id, actor, level="read")

    creator_name: str | None = None
    if run.created_by_id is not None:
        u = await db.get(User, run.created_by_id)
        if u is not None:
            creator_name = u.full_name

    return BulkGenerationRunDetail(
        id=run.id,
        table_id=run.table_id,
        name=run.name,
        status=run.status,  # type: ignore[arg-type]
        total=run.total,
        done=run.done,
        failed=run.failed,
        skipped=run.skipped,
        error=run.error,
        created_by_id=run.created_by_id,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_by_name=creator_name,
    )


@router.post("/gen-runs/{run_id}/cancel", response_model=BulkGenerationRunRead)
async def cancel_gen_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkGenerationRun:
    """Request cancellation of an in-flight generation run.

    Sets status='cancelled' immediately. Workers consult run.status
    before processing each cell and bail out (incrementing skipped)
    when they see this. The run's finished_at is stamped on the
    transition to a terminal state by the LAST worker — not here —
    so the duration in the UI reflects actual elapsed work.

    No-op on terminal states (done / failed / cancelled): returns the
    current row without bumping anything.
    """
    run = await _get_gen_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")

    if run.status in ("cancelled", "done", "failed"):
        return run

    run.status = "cancelled"
    # If no cells finish after this point (rare — the queue was
    # already drained except for ours, or the worker is bottlenecked),
    # we still want finished_at populated so the UI doesn't show a
    # cancelled run as "ongoing forever". The worker stamps it on the
    # last counter update; this catches the no-more-updates edge case.
    if (
        run.done + run.failed + run.skipped >= run.total
        and run.finished_at is None
    ):
        run.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


# ---------- Find / replace (content tool) ----------


async def _load_cells_with_meta(
    db: AsyncSession, table_id: int, column_ids: list[int]
) -> list[tuple[BulkTableCell, int, str]]:
    """All non-empty cells of a table (optionally scoped to ``column_ids``),
    each paired with its row position and column name. Ordered by
    (row position, column position) so results read top-to-bottom like the
    grid. Empty cells don't exist in ``bulk_table_cells`` so they're skipped
    for free."""
    q = (
        select(BulkTableCell, BulkTableRow.position, BulkTableColumn.name)
        .join(BulkTableRow, BulkTableRow.id == BulkTableCell.row_id)
        .join(BulkTableColumn, BulkTableColumn.id == BulkTableCell.column_id)
        .where(BulkTableRow.table_id == table_id)
    )
    if column_ids:
        q = q.where(BulkTableCell.column_id.in_(column_ids))
    q = q.order_by(BulkTableRow.position, BulkTableColumn.position)
    rows = (await db.execute(q)).all()
    return [(cell, pos, name) for cell, pos, name in rows]


async def _get_replace_run_or_404(
    db: AsyncSession, run_id: int
) -> FindReplaceRun:
    run = await db.get(FindReplaceRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Replace run not found")
    return run


@router.post("/tables/{table_id}/find", response_model=FindResponse)
async def find_in_table(
    table_id: int,
    payload: FindRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FindResponse:
    """Read-only search. Returns the matching cells (paginated) plus total
    occurrence + cell counts. Persists nothing."""
    await _get_table_or_404(db, table_id, actor, level="read")
    try:
        compiled = compile_pattern(
            payload.pattern,
            is_regex=payload.is_regex,
            case_sensitive=payload.case_sensitive,
        )
    except InvalidPattern as e:
        raise HTTPException(status_code=400, detail=str(e))

    matched: list[tuple[BulkTableCell, int, str, int]] = []
    total_matches = 0
    for cell, row_pos, col_name in await _load_cells_with_meta(
        db, table_id, payload.column_ids
    ):
        if not cell.value:
            continue
        n = count_matches(compiled, cell.value, whole_cell=payload.whole_cell)
        if n > 0:
            total_matches += n
            matched.append((cell, row_pos, col_name, n))

    start = (payload.page - 1) * payload.page_size
    page = matched[start : start + payload.page_size]
    return FindResponse(
        total_matches=total_matches,
        total_cells=len(matched),
        page=payload.page,
        page_size=payload.page_size,
        items=[
            MatchedCell(
                row_id=c.row_id,
                row_position=rp,
                column_id=c.column_id,
                column_name=cn,
                value=c.value or "",
                status=c.status,  # type: ignore[arg-type]
                match_count=n,
            )
            for c, rp, cn, n in page
        ],
    )


@router.post(
    "/tables/{table_id}/replace",
    response_model=FindReplaceRunRead,
    status_code=status.HTTP_201_CREATED,
)
async def replace_in_table(
    table_id: int,
    payload: ReplaceRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FindReplaceRun:
    """Apply the replacement across EVERY matching cell at once and record a
    revertable run with a full before/after snapshot. 400 when nothing
    matched (no empty run is created)."""
    await _get_table_or_404(db, table_id, actor, level="write")
    try:
        compiled = compile_pattern(
            payload.pattern,
            is_regex=payload.is_regex,
            case_sensitive=payload.case_sensitive,
        )
    except InvalidPattern as e:
        raise HTTPException(status_code=400, detail=str(e))

    snapshot: list[dict] = []
    total_matches = 0
    for cell, _row_pos, _col_name in await _load_cells_with_meta(
        db, table_id, payload.column_ids
    ):
        if not cell.value:
            continue
        new_value, n = apply_replace(
            compiled,
            cell.value,
            payload.replacement,
            is_regex=payload.is_regex,
            whole_cell=payload.whole_cell,
        )
        if n > 0 and new_value != cell.value:
            snapshot.append(
                {
                    "row_id": cell.row_id,
                    "column_id": cell.column_id,
                    "old_value": cell.value,
                    "old_status": cell.status,
                    "new_value": new_value,
                }
            )
            total_matches += n
            # Preserve the cell's status (a targeted text fix isn't a
            # regeneration) but drop any cached translation — it no longer
            # matches the source, same invariant the upsert path enforces.
            cell.value = new_value
            if cell.translations is not None:
                cell.translations = None

    if not snapshot:
        raise HTTPException(
            status_code=400, detail="No matches found — nothing to replace."
        )

    run = FindReplaceRun(
        table_id=table_id,
        pattern=payload.pattern,
        replacement=payload.replacement,
        is_regex=payload.is_regex,
        case_sensitive=payload.case_sensitive,
        whole_cell=payload.whole_cell,
        column_ids=list(payload.column_ids),
        match_count=total_matches,
        cell_count=len(snapshot),
        status="applied",
        snapshot=snapshot,
        created_by_id=actor.id,
    )
    db.add(run)
    await _bump_table_updated(db, table_id)
    await db.commit()
    await db.refresh(run)
    return run


@router.get(
    "/tables/{table_id}/replace-runs",
    response_model=list[FindReplaceRunRead],
)
async def list_replace_runs(
    table_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FindReplaceRun]:
    """Replace history for a table, newest first."""
    await _get_table_or_404(db, table_id, actor, level="read")
    runs = (
        (
            await db.execute(
                select(FindReplaceRun)
                .where(FindReplaceRun.table_id == table_id)
                .order_by(FindReplaceRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(runs)


@router.get("/replace-runs/{run_id}", response_model=FindReplaceRunDetail)
async def get_replace_run(
    run_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FindReplaceRunDetail:
    """Run metadata + the affected cells (paginated) with before/after and a
    per-cell ``drifted`` flag (current value no longer matches what the
    replace wrote). ``drifted_count`` is computed across the whole run."""
    run = await _get_replace_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="read")

    snap: list[dict] = run.snapshot or []
    row_ids = {e["row_id"] for e in snap}
    col_ids = {e["column_id"] for e in snap}

    cur: dict[tuple[int, int], BulkTableCell] = {}
    row_pos: dict[int, int] = {}
    col_name: dict[int, str] = {}
    if row_ids and col_ids:
        cur_cells = (
            (
                await db.execute(
                    select(BulkTableCell).where(
                        BulkTableCell.row_id.in_(row_ids),
                        BulkTableCell.column_id.in_(col_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        cur = {(c.row_id, c.column_id): c for c in cur_cells}
        row_pos = {
            rid: pos
            for rid, pos in (
                await db.execute(
                    select(BulkTableRow.id, BulkTableRow.position).where(
                        BulkTableRow.id.in_(row_ids)
                    )
                )
            ).all()
        }
        col_name = {
            cid: name
            for cid, name in (
                await db.execute(
                    select(BulkTableColumn.id, BulkTableColumn.name).where(
                        BulkTableColumn.id.in_(col_ids)
                    )
                )
            ).all()
        }

    drifted_count = 0
    for e in snap:
        c = cur.get((e["row_id"], e["column_id"]))
        cur_val = c.value if c is not None else None
        if cur_val != e["new_value"]:
            drifted_count += 1

    # Recompile the run's pattern once to recover per-cell match spans for
    # the before/after highlight. If it somehow no longer compiles, fall
    # back to whole-value segments (no highlight) rather than failing.
    compiled = None
    try:
        compiled = compile_pattern(
            run.pattern,
            is_regex=run.is_regex,
            case_sensitive=run.case_sensitive,
        )
    except InvalidPattern:
        compiled = None

    start = (page - 1) * page_size
    page_snap = snap[start : start + page_size]
    items: list[ReplacedCell] = []
    for e in page_snap:
        c = cur.get((e["row_id"], e["column_id"]))
        cur_val = c.value if c is not None else None
        cur_status = c.status if c is not None else "empty"
        old_v = e["old_value"]
        new_v = e["new_value"]
        drifted = cur_val != new_v
        # old side (struck matches) + the green "what the replace inserted"
        # new side both come from the regex match spans.
        if compiled is not None and old_v is not None:
            old_segs, replace_new_segs = segment_diff(
                compiled,
                old_v,
                run.replacement,
                is_regex=run.is_regex,
                whole_cell=run.whole_cell,
            )
        else:
            old_segs = [{"text": old_v or "", "changed": False}]
            replace_new_segs = [{"text": new_v or "", "changed": False}]

        # When the cell was edited after the replace, the "after" column
        # shows the LIVE value with the later edit highlighted (amber),
        # diffed against what the replace wrote. Otherwise it shows the
        # replace result with the inserted text highlighted (green).
        if drifted:
            new_segs = (
                drift_segments(new_v or "", cur_val)
                if cur_val is not None
                else []
            )
        else:
            new_segs = replace_new_segs
        items.append(
            ReplacedCell(
                row_id=e["row_id"],
                row_position=row_pos.get(e["row_id"], 0),
                column_id=e["column_id"],
                column_name=col_name.get(e["column_id"], "—"),
                old_value=old_v,
                new_value=new_v,
                current_value=cur_val,
                current_status=cur_status,  # type: ignore[arg-type]
                drifted=drifted,
                old_segments=old_segs,  # type: ignore[arg-type]
                new_segments=new_segs,  # type: ignore[arg-type]
            )
        )

    return FindReplaceRunDetail(
        id=run.id,
        table_id=run.table_id,
        name=run.name,
        pattern=run.pattern,
        replacement=run.replacement,
        is_regex=run.is_regex,
        case_sensitive=run.case_sensitive,
        whole_cell=run.whole_cell,
        column_ids=run.column_ids,
        match_count=run.match_count,
        cell_count=run.cell_count,
        status=run.status,  # type: ignore[arg-type]
        created_by_id=run.created_by_id,
        created_at=run.created_at,
        reverted_at=run.reverted_at,
        created_by_name=await _resolve_creator_name(db, run.created_by_id),
        page=page,
        page_size=page_size,
        total_cells=len(snap),
        drifted_count=drifted_count,
        items=items,
    )


@router.post("/replace-runs/{run_id}/revert", response_model=FindReplaceRunRead)
async def revert_replace_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FindReplaceRun:
    """Restore every cell this run changed to its pre-replace value. Writes
    through the normal cell path (clears stale translations). Idempotent:
    a no-op on an already-reverted run. Note this discards any edits made
    to those cells after the replace — the run page surfaces a drift count
    so the operator knows before clicking."""
    run = await _get_replace_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")

    if run.status == "reverted":
        return run

    # Valid (row, column) pairs that still belong to this table — so a
    # deleted row/column doesn't get a resurrected orphan cell.
    valid_rows = {
        rid
        for (rid,) in (
            await db.execute(
                select(BulkTableRow.id).where(
                    BulkTableRow.table_id == run.table_id
                )
            )
        ).all()
    }
    valid_cols = {
        cid
        for (cid,) in (
            await db.execute(
                select(BulkTableColumn.id).where(
                    BulkTableColumn.table_id == run.table_id
                )
            )
        ).all()
    }

    for e in run.snapshot or []:
        rid, cid = e["row_id"], e["column_id"]
        if rid not in valid_rows or cid not in valid_cols:
            continue
        cell = (
            await db.execute(
                select(BulkTableCell).where(
                    BulkTableCell.row_id == rid,
                    BulkTableCell.column_id == cid,
                )
            )
        ).scalar_one_or_none()
        old_value = e["old_value"]
        old_status = e.get("old_status") or _default_status_for(old_value)
        if cell is None:
            db.add(
                BulkTableCell(
                    row_id=rid,
                    column_id=cid,
                    value=old_value,
                    status=old_status,
                )
            )
        else:
            if cell.value != old_value and cell.translations is not None:
                cell.translations = None
            cell.value = old_value
            cell.status = old_status

    run.status = "reverted"
    run.reverted_at = datetime.now(timezone.utc)
    await _bump_table_updated(db, run.table_id)
    await db.commit()
    await db.refresh(run)
    return run


# ---------- Structure & Formatting (content tool) ----------


async def _get_sf_run_or_404(
    db: AsyncSession, run_id: int
) -> StructureFormatRun:
    run = await db.get(StructureFormatRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post(
    "/tables/{table_id}/structure-format/preview",
    response_model=StructureFormatPreview,
)
async def structure_format_preview(
    table_id: int,
    payload: StructureFormatRequest,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StructureFormatPreview:
    """Dry run (writes nothing): the cells the selected transforms WOULD change
    — counts + a paginated sample with the same Applied / Changes view as the
    result table — so the user sees the scope before applying."""
    await _get_table_or_404(db, table_id, actor, level="read")
    ops = [op for op in SF_OPERATIONS if op in set(payload.operations)]
    if not ops:
        raise HTTPException(
            status_code=400, detail="Select at least one operation."
        )

    candidates = 0
    # Lightweight rows (no values retained) for changed cells, so the count is
    # exact; the page's diff is computed only for the slice that's shown.
    changed: list[tuple[int, int, int, str, str, str, list[str]]] = []
    for cell, row_pos, col_name in await _load_cells_with_meta(
        db, table_id, payload.column_ids
    ):
        if not cell.value or not cell.value.strip():
            continue
        candidates += 1
        new_value, applied = sf_apply_traced(cell.value, ops)
        if new_value != cell.value:
            changed.append(
                (
                    row_pos,
                    cell.row_id,
                    cell.column_id,
                    col_name,
                    cell.value,
                    new_value,
                    applied,
                )
            )

    start = (page - 1) * page_size
    page_rows = changed[start : start + page_size]
    items = [
        StructureFormatPreviewCell(
            row_id=rid,
            row_position=rp,
            column_id=cid,
            column_name=cn,
            applied_ops=applied,
            change_segments=[
                UnifiedSegment(**s) for s in condense_unified(old, new)
            ],
        )
        for (rp, rid, cid, cn, old, new, applied) in page_rows
    ]
    return StructureFormatPreview(
        candidates=candidates,
        would_change=len(changed),
        page=page,
        page_size=page_size,
        items=items,
    )


@router.post(
    "/tables/{table_id}/structure-format",
    response_model=StructureFormatRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def structure_format_apply(
    table_id: int,
    payload: StructureFormatRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StructureFormatRun:
    """Queue a structure-format run (202) and process it in a Celery worker
    with live progress — the apply scales to large tables without blocking the
    request. Poll ``GET /structure-format-runs/{id}``."""
    await _get_table_or_404(db, table_id, actor, level="write")
    ops = [op for op in SF_OPERATIONS if op in set(payload.operations)]
    if not ops:
        raise HTTPException(
            status_code=400, detail="Select at least one operation."
        )
    if payload.column_ids:
        await _verify_columns_in_table(db, table_id, payload.column_ids)

    run = StructureFormatRun(
        table_id=table_id,
        operations=ops,
        column_ids=list(payload.column_ids),
        status="queued",
        created_by_id=actor.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    run_sf.delay(run.id)
    return run


@router.get(
    "/tables/{table_id}/structure-format-runs",
    response_model=list[StructureFormatRunRead],
)
async def list_structure_format_runs(
    table_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StructureFormatRun]:
    """Structure-format history for a table, newest first."""
    await _get_table_or_404(db, table_id, actor, level="read")
    runs = (
        (
            await db.execute(
                select(StructureFormatRun)
                .where(StructureFormatRun.table_id == table_id)
                .order_by(StructureFormatRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(runs)


@router.get(
    "/structure-format-runs/{run_id}",
    response_model=StructureFormatRunDetail,
)
async def get_structure_format_run(
    run_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    op: str | None = Query(default=None),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StructureFormatRunDetail:
    """Run state (status/progress) + the CHANGED cells (paginated) with
    before/after diff and a per-cell ``drifted`` flag. The run page polls this
    every ~2s while active, then stops on a terminal status. ``op`` filters to
    cells where that transform actually applied."""
    run = await _get_sf_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="read")

    # Only 'done' cells (the ones that actually changed) appear in results.
    base = select(StructureFormatCell).where(
        StructureFormatCell.run_id == run_id,
        StructureFormatCell.state == "done",
    )
    if op in SF_OPERATIONS:
        base = base.where(StructureFormatCell.applied_ops.contains([op]))
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(
                    StructureFormatCell.row_position, StructureFormatCell.id
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    # Current values for the shown cells → drift detection + the "after" side.
    keys = [(c.row_id, c.column_id) for c in rows]
    cur: dict[tuple[int, int], tuple[str | None, str]] = {}
    if keys:
        cur_cells = (
            (
                await db.execute(
                    select(BulkTableCell).where(
                        BulkTableCell.row_id.in_([k[0] for k in keys]),
                        BulkTableCell.column_id.in_([k[1] for k in keys]),
                    )
                )
            )
            .scalars()
            .all()
        )
        cur = {
            (c.row_id, c.column_id): (c.value, c.status) for c in cur_cells
        }

    # drifted_count across the whole run (cheap: current != new_value).
    drifted_count = (
        await db.execute(
            text(
                """
                SELECT count(*) FROM structure_format_cells sfc
                LEFT JOIN bulk_table_cells bc
                  ON bc.row_id = sfc.row_id AND bc.column_id = sfc.column_id
                WHERE sfc.run_id = :rid AND sfc.state = 'done'
                  AND bc.value IS DISTINCT FROM sfc.new_value
                """
            ),
            {"rid": run_id},
        )
    ).scalar_one()

    items: list[StructureFormatCellSchema] = []
    for c in rows:
        cur_val, cur_status = cur.get(
            (c.row_id, c.column_id), (None, "empty")
        )
        old_v = c.old_value
        new_v = c.new_value
        drifted = cur_val != new_v
        # Condensed single-pane diff (old→new) keeps the changes visible in a
        # huge cell; applied_ops (stored) = which transforms touched this cell.
        change_segs = condense_unified(old_v or "", new_v or "")
        items.append(
            StructureFormatCellSchema(
                row_id=c.row_id,
                row_position=c.row_position,
                column_id=c.column_id,
                column_name=c.column_name,
                old_value=old_v,
                new_value=new_v,
                current_value=cur_val,
                current_status=cur_status,  # type: ignore[arg-type]
                drifted=drifted,
                applied_ops=list(c.applied_ops or []),
                change_segments=change_segs,  # type: ignore[arg-type]
            )
        )

    return StructureFormatRunDetail(
        id=run.id,
        table_id=run.table_id,
        name=run.name,
        operations=run.operations,
        column_ids=run.column_ids,
        status=run.status,  # type: ignore[arg-type]
        total=run.total,
        done=run.done,
        failed=run.failed,
        cell_count=run.cell_count,
        reverted_at=run.reverted_at,
        error=run.error,
        created_by_id=run.created_by_id,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_by_name=await _resolve_creator_name(db, run.created_by_id),
        page=page,
        page_size=page_size,
        total_cells=int(total),
        drifted_count=int(drifted_count),
        items=items,
    )


@router.post(
    "/structure-format-runs/{run_id}/revert",
    response_model=StructureFormatRunRead,
)
async def revert_structure_format_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StructureFormatRun:
    """Restore every cell this run changed to its pre-run value. Idempotent;
    skips rows/columns that no longer exist. Discards edits made after the
    run (the run page surfaces a drift count first)."""
    run = await _get_sf_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.reverted_at is not None:
        return run

    valid_rows = {
        rid
        for (rid,) in (
            await db.execute(
                select(BulkTableRow.id).where(
                    BulkTableRow.table_id == run.table_id
                )
            )
        ).all()
    }
    valid_cols = {
        cid
        for (cid,) in (
            await db.execute(
                select(BulkTableColumn.id).where(
                    BulkTableColumn.table_id == run.table_id
                )
            )
        ).all()
    }

    changed_cells = (
        (
            await db.execute(
                select(StructureFormatCell).where(
                    StructureFormatCell.run_id == run_id,
                    StructureFormatCell.state == "done",
                )
            )
        )
        .scalars()
        .all()
    )
    for sfc in changed_cells:
        rid, cid = sfc.row_id, sfc.column_id
        if rid not in valid_rows or cid not in valid_cols:
            continue
        cell = (
            await db.execute(
                select(BulkTableCell).where(
                    BulkTableCell.row_id == rid,
                    BulkTableCell.column_id == cid,
                )
            )
        ).scalar_one_or_none()
        old_value = sfc.old_value
        old_status = sfc.old_status or _default_status_for(old_value)
        if cell is None:
            db.add(
                BulkTableCell(
                    row_id=rid,
                    column_id=cid,
                    value=old_value,
                    status=old_status,
                )
            )
        else:
            if cell.value != old_value and cell.translations is not None:
                cell.translations = None
            cell.value = old_value
            cell.status = old_status

    run.reverted_at = datetime.now(timezone.utc)
    await _bump_table_updated(db, run.table_id)
    await db.commit()
    await db.refresh(run)
    return run


@router.post(
    "/structure-format-runs/{run_id}/cancel",
    response_model=StructureFormatRunRead,
)
async def cancel_structure_format_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StructureFormatRun:
    """Stop an in-flight run. Cells already processed keep their change (and
    are revertable); the rest are left untouched. No-op on terminal states."""
    run = await _get_sf_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("done", "failed", "cancelled"):
        return run
    run.status = "cancelled"
    if run.finished_at is None:
        run.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


@router.post(
    "/structure-format-runs/{run_id}/resume",
    response_model=StructureFormatRunRead,
)
async def resume_structure_format_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StructureFormatRun:
    """Re-enqueue a stalled run's remaining cells. No-op on terminal states."""
    run = await _get_sf_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("done", "failed", "cancelled"):
        return run
    resume_sf.delay(run.id)
    return run


@router.patch(
    "/structure-format-runs/{run_id}",
    response_model=StructureFormatRunRead,
)
async def rename_structure_format_run(
    run_id: int,
    payload: RunRename,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StructureFormatRun:
    run = await _get_sf_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    run.name = _norm_run_name(payload)
    await db.commit()
    await db.refresh(run)
    return run


@router.delete(
    "/structure-format-runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_structure_format_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    run = await _get_sf_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    await db.delete(run)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Link checker (content tool) ----------


async def _get_link_check_run_or_404(
    db: AsyncSession, run_id: int
) -> LinkCheckRun:
    run = await db.get(LinkCheckRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Link-check run not found")
    return run


async def _verify_columns_in_table(
    db: AsyncSession, table_id: int, column_ids: list[int]
) -> None:
    if not column_ids:
        return
    found = {
        cid
        for (cid,) in (
            await db.execute(
                select(BulkTableColumn.id).where(
                    BulkTableColumn.table_id == table_id,
                    BulkTableColumn.id.in_(column_ids),
                )
            )
        ).all()
    }
    missing = [c for c in column_ids if c not in found]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Unknown column id(s): {missing}"
        )


@router.post(
    "/tables/{table_id}/link-check",
    response_model=LinkCheckRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_link_check(
    table_id: int,
    payload: LinkCheckRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkCheckRun:
    """Queue a link-check run and return it immediately (202). The crawl,
    when enabled, runs in a Celery worker; poll ``GET /link-check-runs/{id}``
    for progress and results."""
    await _get_table_or_404(db, table_id, actor, level="read")

    if payload.translation is not None:
        run = await _create_translation_run(db, table_id, actor, payload.translation)
    else:
        await _verify_columns_in_table(db, table_id, payload.column_ids)
        if payload.expected_column_ids:
            await _verify_columns_in_table(db, table_id, payload.expected_column_ids)
        run = LinkCheckRun(
            table_id=table_id,
            created_by_id=actor.id,
            status="queued",
            column_ids=list(payload.column_ids),
            expected_column_ids=list(payload.expected_column_ids),
            check_juxtapose=payload.check_juxtapose,
            check_crawl=payload.check_crawl,
            include_ok=payload.include_ok,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

    seed_link_check.delay(run.id)
    return run


async def _create_translation_run(
    db: AsyncSession,
    table_id: int,
    actor: User,
    cfg: "TranslationCheckConfig",
) -> LinkCheckRun:
    """Build a queued translation-mode run.

    The three column roles are validated; the bulk textareas are parsed into
    normalized lists stored in ``translation_config``. ``column_ids`` is the
    translated column (the scanned output); ``expected_column_ids`` is left
    empty here — the seed materializes the computed expected-links column and
    sets it before juxtaposing, so AI-fix / revert read it like any other run.
    The run is flagged ``check_juxtapose`` so the run page shows the right
    counters/filters and offers the AI fix."""
    from app.services.translation_links import parse_domains, parse_exceptions

    role_cols = [
        cfg.original_column_id,
        cfg.translated_column_id,
        cfg.lang_column_id,
    ]
    await _verify_columns_in_table(
        db, table_id, role_cols + list(cfg.internal_domain_column_ids)
    )
    stored = {
        "original_column_id": cfg.original_column_id,
        "translated_column_id": cfg.translated_column_id,
        "lang_column_id": cfg.lang_column_id,
        "internal_domain_column_ids": list(cfg.internal_domain_column_ids),
        "product_domains": parse_domains(cfg.product_domain),
        "exceptions": parse_exceptions(cfg.exceptions),
        "internal_treatment": cfg.internal_treatment,
        "external_treatment": cfg.external_treatment,
    }
    run = LinkCheckRun(
        table_id=table_id,
        created_by_id=actor.id,
        status="queued",
        column_ids=[cfg.translated_column_id],
        expected_column_ids=[],
        check_juxtapose=True,
        check_crawl=False,
        include_ok=False,
        translation_config=stored,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@router.get(
    "/tables/{table_id}/link-check-runs",
    response_model=list[LinkCheckRunRead],
)
async def list_link_check_runs(
    table_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LinkCheckRun]:
    """Link-check history for a table, newest first."""
    await _get_table_or_404(db, table_id, actor, level="read")
    runs = (
        (
            await db.execute(
                select(LinkCheckRun)
                .where(LinkCheckRun.table_id == table_id)
                .order_by(LinkCheckRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(runs)


@router.get("/link-check-runs/{run_id}", response_model=LinkCheckRunDetail)
async def get_link_check_run(
    run_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    problem: str | None = Query(default=None),
    status_code: int | None = Query(default=None),
    q: str | None = Query(default=None),
    q_negate: bool = Query(default=False),
    resolution: str | None = Query(default=None),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkCheckRunDetail:
    """Run state (counters/progress) + the flagged links (paginated). The run
    page polls this every ~2s while active, then stops on a terminal status.

    Optional filters (server-side so they hold across pages): ``problem``
    (omitted|hallucinated|broken|ok), ``status_code``, and ``q`` (link
    substring; ``q_negate`` flips it to "does not contain")."""
    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="read")

    base = select(LinkCheckViolation).where(LinkCheckViolation.run_id == run_id)
    if problem in ("omitted", "hallucinated", "broken", "ok"):
        base = base.where(LinkCheckViolation.problem == problem)
    if status_code is not None:
        base = base.where(LinkCheckViolation.status_code == status_code)
    # Resolution from the in-place AI re-verify: untouched = never fixed.
    if resolution == "untouched":
        base = base.where(LinkCheckViolation.resolution.is_(None))
    elif resolution in ("solved", "unsolved"):
        base = base.where(LinkCheckViolation.resolution == resolution)
    if q and q.strip():
        pat = f"%{q.strip()}%"
        base = base.where(
            LinkCheckViolation.link.notilike(pat)
            if q_negate
            else LinkCheckViolation.link.ilike(pat)
        )

    total = (
        await db.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar_one()

    rows = (
        (
            await db.execute(
                base.order_by(
                    LinkCheckViolation.row_position,
                    LinkCheckViolation.problem,
                    LinkCheckViolation.id,
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    # Distinct status codes across the whole run (unfiltered) for the dropdown.
    codes = (
        (
            await db.execute(
                select(LinkCheckViolation.status_code)
                .where(
                    LinkCheckViolation.run_id == run_id,
                    LinkCheckViolation.status_code.isnot(None),
                )
                .distinct()
                .order_by(LinkCheckViolation.status_code)
            )
        )
        .scalars()
        .all()
    )

    # Per-status-class breakdown for the crawl overview (unique-URL based,
    # from the crawl-targets table — consistent with ok_count/broken_count,
    # and the only source that has 2xx/3xx codes when include_ok is off).
    # "Битые" is now exactly 404; 5xx/3xx/2xx are whole-class buckets.
    s_2xx = s_3xx = s_404 = s_5xx = 0
    if run.check_crawl:
        agg = (
            await db.execute(
                select(
                    func.count().filter(LinkCheckCrawlTarget.status_code == 404),
                    func.count().filter(
                        LinkCheckCrawlTarget.status_code.between(500, 599)
                    ),
                    func.count().filter(
                        LinkCheckCrawlTarget.status_code.between(300, 399)
                    ),
                    func.count().filter(
                        LinkCheckCrawlTarget.status_code.between(200, 299)
                    ),
                ).where(LinkCheckCrawlTarget.run_id == run_id)
            )
        ).one()
        s_404, s_5xx, s_3xx, s_2xx = (int(x) for x in agg)

    return LinkCheckRunDetail(
        id=run.id,
        table_id=run.table_id,
        name=run.name,
        status=run.status,  # type: ignore[arg-type]
        column_ids=run.column_ids,
        expected_column_ids=run.expected_column_ids,
        check_juxtapose=run.check_juxtapose,
        check_crawl=run.check_crawl,
        include_ok=run.include_ok,
        total_links=run.total_links,
        crawled=run.crawled,
        ok_count=run.ok_count,
        broken_count=run.broken_count,
        omitted_count=run.omitted_count,
        hallucinated_count=run.hallucinated_count,
        error=run.error,
        created_by_id=run.created_by_id,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        translation_config=run.translation_config,
        created_by_name=await _resolve_creator_name(db, run.created_by_id),
        page=page,
        page_size=page_size,
        total_violations=total,
        status_codes_present=list(codes),
        status_2xx=s_2xx,
        status_3xx=s_3xx,
        status_404=s_404,
        status_5xx=s_5xx,
        items=[LinkViolationRead.model_validate(v) for v in rows],
    )


@router.get(
    "/link-check-runs/{run_id}/translation-table",
    response_model=TranslationTableResponse,
)
async def get_translation_table(
    run_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TranslationTableResponse:
    """The translation raw-table view: per row, the 4-column link breakdown
    (original / expected / translation / mismatches), computed on demand from
    the source columns + the run's translation_config. Nothing is materialized
    into the bulk table. 400 if the run isn't a translation run."""
    from app.services.translation_links import compute_row_breakdown, parse_domains

    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="read")
    cfg = run.translation_config
    if not cfg:
        raise HTTPException(status_code=400, detail="Not a translation run.")

    orig_col = int(cfg["original_column_id"])
    trans_col = int(cfg["translated_column_id"])
    lang_col = int(cfg["lang_column_id"])
    domain_cols = [int(c) for c in cfg.get("internal_domain_column_ids", [])]
    product_domains = cfg.get("product_domains", []) or []
    exceptions = cfg.get("exceptions", []) or []
    internal_t = cfg.get("internal_treatment", "skip")
    external_t = cfg.get("external_treatment", "skip")

    # "Has any links" can only be known after extraction, so we compute every
    # row's breakdown, drop the empty rows, then paginate the filtered set.
    # (Translation tables are bounded — same all-rows scan the seed does.)
    all_rows = (
        await db.execute(
            select(BulkTableRow.id, BulkTableRow.position)
            .where(BulkTableRow.table_id == run.table_id)
            .order_by(BulkTableRow.position)
        )
    ).all()

    by_row: dict[int, dict[int, str | None]] = defaultdict(dict)
    if all_rows:
        cells = (
            (
                await db.execute(
                    select(BulkTableCell)
                    .join(BulkTableRow, BulkTableRow.id == BulkTableCell.row_id)
                    .where(
                        BulkTableRow.table_id == run.table_id,
                        BulkTableCell.column_id.in_(
                            [orig_col, trans_col, lang_col, *domain_cols]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for c in cells:
            by_row[c.row_id][c.column_id] = c.value

    filtered: list[TranslationTableRow] = []
    for rid, pos in all_rows:
        vals = by_row.get(rid, {})
        internal_domains: list[str] = []
        for dc in domain_cols:
            internal_domains += parse_domains(vals.get(dc))
        bd = compute_row_breakdown(
            vals.get(orig_col),
            vals.get(trans_col),
            (vals.get(lang_col) or "").strip(),
            internal_domains=internal_domains,
            product_domains=product_domains,
            exceptions=exceptions,
            internal_treatment=internal_t,
            external_treatment=external_t,
        )
        # Hide rows with no links anywhere.
        if not (
            bd["original"] or bd["expected"] or bd["translation"] or bd["mismatches"]
        ):
            continue
        filtered.append(
            TranslationTableRow(
                row_id=rid,
                row_position=pos,
                original=bd["original"],
                expected=bd["expected"],
                translation=bd["translation"],
                mismatches=bd["mismatches"],
            )
        )

    total = len(filtered)
    start = (page - 1) * page_size
    return TranslationTableResponse(
        page=page,
        page_size=page_size,
        total_rows=total,
        items=filtered[start : start + page_size],
    )


@router.post("/link-check-runs/{run_id}/cancel", response_model=LinkCheckRunRead)
async def cancel_link_check_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkCheckRun:
    """Request cancellation of an in-flight crawl. The worker checks
    ``status`` between crawl batches and stops. No-op on terminal states."""
    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("cancelled", "done", "failed"):
        return run
    run.status = "cancelled"
    # The crawl is fanned out across workers with no single finalizer, so
    # stamp finished_at here; the chunk tasks just stop when they see the
    # cancelled status.
    if run.finished_at is None:
        run.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/link-check-runs/{run_id}/resume", response_model=LinkCheckRunRead)
async def resume_link_check_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkCheckRun:
    """Manually nudge a stalled run: re-enqueue its pending crawl chunks
    (or re-seed if it never started). A watchdog does this automatically for
    stalled runs; this is the operator's immediate override. No-op on
    terminal states."""
    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("done", "failed", "cancelled"):
        return run
    resume_link_check.delay(run.id)
    return run


# ---------- AI link fix (content tool) ----------

_FIXABLE_PROBLEMS = ("omitted", "broken", "hallucinated")


async def _get_link_fix_run_or_404(db: AsyncSession, run_id: int) -> LinkFixRun:
    run = await db.get(LinkFixRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Link-fix run not found")
    return run


@router.post(
    "/tables/{table_id}/link-fix",
    response_model=LinkFixRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_link_fix(
    table_id: int,
    payload: LinkFixRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRun:
    """Start an AI link-fix run off a completed check run.

    Each flagged output cell (in the chosen rows, or all flagged rows) is
    rewritten by the Brain ``fix_links`` prompt: integrate a missing expected
    link, correct a typo'd one, remove a hallucinated one. The run is
    revertable (before/after snapshots) and auto-re-checks the touched rows
    when done.
    """
    await _get_table_or_404(db, table_id, actor, level="write")
    source = await _get_link_check_run_or_404(db, payload.source_run_id)
    if source.table_id != table_id:
        raise HTTPException(status_code=404, detail="Link-check run not found")
    if source.status != "done":
        raise HTTPException(
            status_code=400, detail="The check run must finish before fixing."
        )
    # Translation runs have no expected column — the worker recomputes the
    # localized expected links from the run's translation_config.
    if not source.expected_column_ids and not source.translation_config:
        raise HTTPException(
            status_code=400,
            detail=(
                "Fixing needs an expected-links column. Re-run the check with "
                "‘Compare to expected links’ enabled."
            ),
        )

    # Gather fixable violations from the source run, optionally row-scoped
    # AND filtered to match whatever the run page is currently showing — so
    # "Fix all" after filtering to e.g. hallucinated only touches those.
    vq = select(LinkCheckViolation).where(
        LinkCheckViolation.run_id == source.id,
        LinkCheckViolation.problem.in_(_FIXABLE_PROBLEMS),
    )
    scope = {int(x) for x in payload.row_ids} if payload.row_ids else None
    if scope is not None:
        vq = vq.where(LinkCheckViolation.row_id.in_(scope))
    if payload.problem in _FIXABLE_PROBLEMS:
        vq = vq.where(LinkCheckViolation.problem == payload.problem)
    if payload.status_code is not None:
        vq = vq.where(LinkCheckViolation.status_code == payload.status_code)
    if payload.q and payload.q.strip():
        pat = f"%{payload.q.strip()}%"
        vq = vq.where(
            LinkCheckViolation.link.notilike(pat)
            if payload.q_negate
            else LinkCheckViolation.link.ilike(pat)
        )
    violations = (await db.execute(vq)).scalars().all()

    # Group by (row, column) → the cell to fix.
    grouped: dict[tuple[int, int], dict] = {}
    for v in violations:
        key = (v.row_id, v.column_id)
        g = grouped.get(key)
        if g is None:
            g = {
                "row_position": v.row_position,
                "column_name": v.column_name,
                "violations": [],
            }
            grouped[key] = g
        g["violations"].append(
            {
                "problem": v.problem,
                "link": v.link,
                "detail_code": v.detail_code,
                "status_code": v.status_code,
            }
        )

    if not grouped:
        raise HTTPException(
            status_code=400, detail="Nothing to fix in the selected rows."
        )

    # Resolve where corrected content goes. new_column_name creates a fresh
    # output column (original preserved); target_column_id reuses one; neither
    # = overwrite the scanned source column (target_column_id stays NULL).
    target_column_id: int | None = None
    if payload.new_column_name and payload.new_column_name.strip():
        next_pos = (
            await db.execute(
                select(func.coalesce(func.max(BulkTableColumn.position), -1) + 1)
                .where(BulkTableColumn.table_id == table_id)
            )
        ).scalar_one()
        new_col = BulkTableColumn(
            table_id=table_id,
            position=int(next_pos),
            name=payload.new_column_name.strip()[:120],
            kind="output",
        )
        db.add(new_col)
        await db.flush()
        target_column_id = new_col.id

        # Publish-readiness: the new column must hold EVERY row, not just the
        # flagged ones, so it can be published as a complete column. Copy all
        # cells of the single scanned source column into it up front; the
        # fix workers then overwrite the corrected rows. (Link checks scan a
        # single output column, so there's one unambiguous source.)
        from sqlalchemy import literal
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        src_cols = [int(c) for c in (source.column_ids or [])]
        if src_cols:
            src_col = src_cols[0]
            await db.execute(
                pg_insert(BulkTableCell)
                .from_select(
                    ["row_id", "column_id", "value", "status"],
                    select(
                        BulkTableCell.row_id,
                        literal(new_col.id),
                        BulkTableCell.value,
                        BulkTableCell.status,
                    ).where(BulkTableCell.column_id == src_col),
                )
                .on_conflict_do_nothing(constraint="uq_bulk_cells_row_column")
            )
    elif payload.target_column_id is not None:
        await _verify_columns_in_table(db, table_id, [payload.target_column_id])
        target_column_id = payload.target_column_id

    # Snapshot the original SOURCE content for each affected cell (the
    # before/after display reads this; revert uses the worker's target
    # snapshot).
    row_ids = {r for (r, _c) in grouped}
    col_ids = {c for (_r, c) in grouped}
    value_map: dict[tuple[int, int], str | None] = {}
    existing = (
        (
            await db.execute(
                select(BulkTableCell).where(
                    BulkTableCell.row_id.in_(row_ids),
                    BulkTableCell.column_id.in_(col_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    for c in existing:
        value_map[(c.row_id, c.column_id)] = c.value

    run = LinkFixRun(
        table_id=table_id,
        source_run_id=source.id,
        created_by_id=actor.id,
        status="running",
        target_column_id=target_column_id,
        column_ids=list(source.column_ids or []),
        expected_column_ids=list(source.expected_column_ids or []),
        prompt=(payload.prompt.strip() or None) if payload.prompt else None,
        total=len(grouped),
        started_at=datetime.now(timezone.utc),
        last_progress_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()  # run.id

    cells: list[LinkFixCell] = []
    for (rid, cid), g in grouped.items():
        cells.append(
            LinkFixCell(
                run_id=run.id,
                row_id=rid,
                row_position=g["row_position"],
                column_id=cid,
                column_name=g["column_name"],
                state="pending",
                source_value=value_map.get((rid, cid)),
                violations=g["violations"],
            )
        )
    db.add_all(cells)
    await db.commit()

    cell_ids = [c.id for c in cells]
    for cid in cell_ids:
        fix_cell_task.delay(run.id, cid)

    await db.refresh(run)
    return run


@router.get(
    "/tables/{table_id}/link-fix/default-prompt",
    response_model=LinkFixDefaultPrompt,
)
async def link_fix_default_prompt(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixDefaultPrompt:
    """The prompt the fix modal should default to: the most recent fix job's
    prompt for this table (so "reuse the previously-used prompt" just works),
    falling back to the global Brain ``fix_links`` prompt the first time."""
    await _get_table_or_404(db, table_id, actor, level="read")
    last = (
        await db.execute(
            select(LinkFixRun.prompt)
            .where(
                LinkFixRun.table_id == table_id,
                LinkFixRun.prompt.isnot(None),
            )
            .order_by(LinkFixRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last and last.strip():
        return LinkFixDefaultPrompt(prompt=last)

    from app.services.brain import load_brain

    brain = await load_brain(db)
    prompt = (brain.get("fix_links") or {}).get("prompt") or ""
    return LinkFixDefaultPrompt(prompt=prompt)


@router.get(
    "/tables/{table_id}/link-fix-runs", response_model=list[LinkFixRunRead]
)
async def list_link_fix_runs(
    table_id: int,
    source_run_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LinkFixRun]:
    """Correction-run history for a table, newest first. Pass
    ``source_run_id`` to list only the fixes launched from one check run
    (the Link Checker run page nests them this way)."""
    await _get_table_or_404(db, table_id, actor, level="read")
    q = select(LinkFixRun).where(LinkFixRun.table_id == table_id)
    if source_run_id is not None:
        q = q.where(LinkFixRun.source_run_id == source_run_id)
    runs = (
        (
            await db.execute(
                q.order_by(LinkFixRun.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(runs)


@router.get("/link-fix-runs/{run_id}", response_model=LinkFixRunDetail)
async def get_link_fix_run(
    run_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRunDetail:
    """Fix-run state + the per-cell before/after (paginated). The fix-run page
    polls this every ~2s while active, then stops on a terminal status."""
    run = await _get_link_fix_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="read")

    total = (
        await db.execute(
            select(func.count())
            .select_from(LinkFixCell)
            .where(LinkFixCell.run_id == run_id)
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(LinkFixCell)
                .where(LinkFixCell.run_id == run_id)
                .order_by(LinkFixCell.row_position, LinkFixCell.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return LinkFixRunDetail(
        id=run.id,
        table_id=run.table_id,
        name=run.name,
        source_run_id=run.source_run_id,
        recheck_run_id=run.recheck_run_id,
        target_column_id=run.target_column_id,
        status=run.status,  # type: ignore[arg-type]
        column_ids=run.column_ids,
        expected_column_ids=run.expected_column_ids,
        total=run.total,
        done=run.done,
        failed=run.failed,
        skipped=run.skipped,
        reverted_at=run.reverted_at,
        error=run.error,
        created_by_id=run.created_by_id,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_by_name=await _resolve_creator_name(db, run.created_by_id),
        page=page,
        page_size=page_size,
        total_cells=int(total),
        items=[_fix_cell_read(c) for c in rows],
    )


def _fix_cell_read(c: LinkFixCell) -> LinkFixCellRead:
    """Build the read model with the Before/After char-diff segments
    (only meaningful once the cell is done)."""
    item = LinkFixCellRead.model_validate(c)
    if c.state == "done":
        before = c.source_value or c.old_value or ""
        after = c.new_value or ""
        old_segs, new_segs = diff_segments(before, after)
        item.before_segments = [DiffSegment(**s) for s in old_segs]
        item.after_segments = [DiffSegment(**s) for s in new_segs]
    return item


@router.get(
    "/tables/{table_id}/link-fixes", response_model=list[TableFixedCell]
)
async def list_table_fixed_cells(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TableFixedCell]:
    """Cells corrected by an applied (non-reverted) AI link-fix run, keyed by
    the TARGET cell they landed in. Drives the grid's green tint and the cell
    editor's "Changes" diff view. Latest fix wins when a cell was touched more
    than once."""
    await _get_table_or_404(db, table_id, actor, level="read")
    rows = (
        (
            await db.execute(
                select(LinkFixCell, LinkFixRun.target_column_id)
                .join(LinkFixRun, LinkFixRun.id == LinkFixCell.run_id)
                .where(
                    LinkFixRun.table_id == table_id,
                    LinkFixRun.reverted_at.is_(None),
                    LinkFixCell.state == "done",
                )
                .order_by(LinkFixRun.created_at)
            )
        )
        .all()
    )
    # Last write wins per target cell (rows are ordered oldest-first).
    by_cell: dict[tuple[int, int], LinkFixCell] = {}
    for cell, target_col_id in rows:
        target_col = target_col_id or cell.column_id
        by_cell[(cell.row_id, target_col)] = cell

    out: list[TableFixedCell] = []
    for (row_id, col_id), cell in by_cell.items():
        before = cell.source_value or cell.old_value or ""
        after = cell.new_value or ""
        segs = unified_segments(before, after)
        out.append(
            TableFixedCell(
                row_id=row_id,
                column_id=col_id,
                segments=[UnifiedSegment(**s) for s in segs],
            )
        )
    return out


@router.post("/link-fix-runs/{run_id}/cancel", response_model=LinkFixRunRead)
async def cancel_link_fix_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRun:
    """Stop an in-flight fix. In-flight cells finish; pending cells are
    skipped by the workers. No-op on terminal states."""
    run = await _get_link_fix_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("cancelled", "done", "failed"):
        return run
    run.status = "cancelled"
    if run.finished_at is None:
        run.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/link-fix-runs/{run_id}/resume", response_model=LinkFixRunRead)
async def resume_link_fix_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRun:
    """Re-enqueue a stalled fix run's pending cells. No-op on terminal states."""
    run = await _get_link_fix_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("done", "failed", "cancelled"):
        return run
    resume_link_fix.delay(run.id)
    return run


@router.post("/link-fix-runs/{run_id}/revert", response_model=LinkFixRunRead)
async def revert_link_fix_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRun:
    """Restore the pre-fix value of every cell this run changed.

    Idempotent. A cell is skipped if its current value no longer matches the
    value the fix wrote (someone edited or regenerated it since) — reverting
    would otherwise discard that later change."""
    run = await _get_link_fix_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.reverted_at is not None:
        return run

    cells = (
        (
            await db.execute(
                select(LinkFixCell).where(
                    LinkFixCell.run_id == run_id,
                    LinkFixCell.state == "done",
                )
            )
        )
        .scalars()
        .all()
    )
    for fc in cells:
        # Corrected content lives in the run's target column (or the source
        # column when overwriting).
        target_col = run.target_column_id or fc.column_id
        current = (
            await db.execute(
                select(BulkTableCell.value).where(
                    BulkTableCell.row_id == fc.row_id,
                    BulkTableCell.column_id == target_col,
                )
            )
        ).scalar_one_or_none()
        # Only revert cells still holding exactly what the fix wrote.
        if current == fc.new_value:
            await db.execute(
                update(BulkTableCell)
                .where(
                    BulkTableCell.row_id == fc.row_id,
                    BulkTableCell.column_id == target_col,
                )
                .values(value=fc.old_value, translations=None)
            )

    # Clear the in-place re-verify stamps this run set on the source check
    # run's violations, so they read as "untouched" again.
    if run.source_run_id is not None and cells:
        cell_keys = {(fc.row_id, fc.column_id) for fc in cells}
        rows = [r for r, _c in cell_keys]
        cols = [c for _r, c in cell_keys]
        await db.execute(
            update(LinkCheckViolation)
            .where(
                LinkCheckViolation.run_id == run.source_run_id,
                LinkCheckViolation.row_id.in_(rows),
                LinkCheckViolation.column_id.in_(cols),
            )
            .values(resolution=None)
        )
    run.reverted_at = datetime.now(timezone.utc)
    await _bump_table_updated(db, run.table_id)
    await db.commit()
    await db.refresh(run)
    return run


def _norm_run_name(payload: RunRename) -> str | None:
    n = (payload.name or "").strip()
    return n or None


@router.patch("/link-fix-runs/{run_id}", response_model=LinkFixRunRead)
async def rename_link_fix_run(
    run_id: int,
    payload: RunRename,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRun:
    run = await _get_link_fix_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    run.name = _norm_run_name(payload)
    await db.commit()
    await db.refresh(run)
    return run


@router.delete("/link-fix-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link_fix_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    run = await _get_link_fix_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("queued", "running"):
        raise HTTPException(
            status_code=409, detail="Cancel the run before deleting it."
        )
    await db.delete(run)  # cascades link_fix_cells
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/link-check-runs/{run_id}", response_model=LinkCheckRunRead)
async def rename_link_check_run(
    run_id: int,
    payload: RunRename,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkCheckRun:
    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    run.name = _norm_run_name(payload)
    await db.commit()
    await db.refresh(run)
    return run


@router.delete("/link-check-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link_check_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("queued", "running"):
        raise HTTPException(
            status_code=409, detail="Cancel the run before deleting it."
        )
    await db.delete(run)  # cascades violations + crawl targets
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/replace-runs/{run_id}", response_model=FindReplaceRunRead)
async def rename_replace_run(
    run_id: int,
    payload: RunRename,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FindReplaceRun:
    run = await _get_replace_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    run.name = _norm_run_name(payload)
    await db.commit()
    await db.refresh(run)
    return run


@router.delete("/replace-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_replace_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    run = await _get_replace_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    await db.delete(run)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/gen-runs/{run_id}", response_model=BulkGenerationRunRead)
async def rename_gen_run(
    run_id: int,
    payload: RunRename,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkGenerationRun:
    run = await _get_gen_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    run.name = _norm_run_name(payload)
    await db.commit()
    await db.refresh(run)
    return run


@router.delete("/gen-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gen_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    run = await _get_gen_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if run.status in ("queued", "running"):
        raise HTTPException(
            status_code=409, detail="Cancel the run before deleting it."
        )
    await db.delete(run)  # cells.generation_run_id FK is SET NULL
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tables/{table_id}/export.csv")
async def export_csv(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t = await _get_table_or_404(db, table_id, actor, level="read", full=True)
    csv_text = await build_table_csv(db, t)
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in t.name)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'},
    )


# ---------- Autotool (3rd publishing mode) ----------
#
# Enabling exposes the table's CSV at an unauthenticated, unguessable URL
# (/autotool/<token>.csv, served by app/api/autotool.py) so the external
# Autotool proxy can fetch it. Gated by "write" access — anyone who can edit
# the table can expose it. Disabling clears the token so the public link dies
# at once. The toggle returns a lightweight AutotoolState (not the full table)
# so a one-click action doesn't ship every cell.


@router.post("/tables/{table_id}/autotool", response_model=AutotoolState)
async def enable_autotool(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutotoolState:
    t = await _get_table_or_404(db, table_id, actor, level="write")
    if not t.autotool_token:
        t.autotool_token = uuid.uuid4().hex  # 32 hex chars, 128 bits
    t.autotool_enabled = True
    # Capture before commit; expire_on_commit would otherwise require a reload.
    token = t.autotool_token
    await db.commit()
    return AutotoolState(
        autotool_enabled=True,
        autotool_token=token,
        csv_path=f"/autotool/{token}.csv",
    )


@router.delete("/tables/{table_id}/autotool", response_model=AutotoolState)
async def disable_autotool(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutotoolState:
    t = await _get_table_or_404(db, table_id, actor, level="write")
    # Drop the token, not just the flag, so a leaked URL can never be revived
    # by re-enabling — the next enable mints a brand-new token.
    t.autotool_enabled = False
    t.autotool_token = None
    await db.commit()
    return AutotoolState(autotool_enabled=False, autotool_token=None, csv_path=None)
