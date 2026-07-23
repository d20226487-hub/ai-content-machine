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
import json
import uuid
from collections import defaultdict
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from decimal import Decimal

from fastapi.responses import StreamingResponse
from sqlalchemy import case, delete, func, or_, select, text, update
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
    GdocsImportRun,
    LinkCheckCrawlTarget,
    LinkCheckDismissal,
    LinkCheckRun,
    LinkCheckViolation,
    LinkFixCell,
    LinkFixRun,
    NormalizeRun,
    StructureFormatCell,
    StructureFormatRun,
    User,
)
from app.db.session import get_db
from app.schemas.bulk import (
    AutotoolEnableRequest,
    AutotoolState,
    BulkGenerationRunDetail,
    BulkGenerationRunRead,
    CellCostRead,
    CellsBatchUpsert,
    CellUpsert,
    ClearValuesRequest,
    ClearValuesResponse,
    ColumnCostRead,
    ColumnGenHealthRead,
    ColumnCreate,
    ColumnRead,
    ColumnUpdate,
    ColumnValuesResponse,
    DiffBlock,
    DismissRequest,
    FindReplaceRunDetail,
    FindReplaceRunRead,
    FindRequest,
    FindResponse,
    FolderCreate,
    FolderRead,
    FolderUpdate,
    GdocsImportRunRead,
    GeneratePreviewResponse,
    GenerateRequest,
    UnmappedColumn,
    GenerateResponse,
    LinkCheckRequest,
    LinkCheckRunDetail,
    LinkCheckRunRead,
    LinkFixCellRead,
    LinkFixDefaultPrompt,
    LinkFixRequest,
    LinkFixRevertResult,
    LinkFixRunDetail,
    LinkFixRunRead,
    LinkViolationRead,
    MatchedCell,
    NormalizeApplyRequest,
    NormalizedCell,
    NormalizePreview,
    NormalizePreviewCell,
    NormalizePreviewRequest,
    NormalizeRunDetail,
    NormalizeRunRead,
    ReplacedCell,
    ReplaceRequest,
    RowRead,
    RunRename,
    StructureFormatCell as StructureFormatCellSchema,
    StructureFormatPreview,
    StructureFormatPreviewCell,
    StructureFormatRequest,
    StripLinksRequest,
    StructureFormatRunDetail,
    StructureFormatRunRead,
    TableBulkMove,
    TableCreate,
    TableFixedCell,
    UnifiedSegment,
    AlignedRow,
    TableListItem,
    TableListResponse,
    TranslationCheckConfig,
    TranslationLinkTag,
    TranslationTableResponse,
    TranslationTableRow,
    TableCostRead,
    TableGenHealthRead,
    ToolCostRead,
    TableRead,
    TableUpdate,
    TableUpdateRequest,
    TableUpdateResult,
    TrashBulkIds,
)
from app.schemas.csv_export import CsvExportJobRead
from app.schemas.share import ShareLinkRead
from app.services import csv_export as csv_export_svc
from app.services.bulk_csv import build_table_csv, content_disposition, stream_table_csv
from app.tasks.csv_export import build_csv_export
from app.services.provider_cache import get_enabled_providers
from app.services.find_replace import (
    InvalidPattern,
    aligned_diff,
    apply_rules,
    compile_rules,
    condense_unified,
    count_matches_rules,
    diff_segments,
    drift_segments,
    parse_finds,
    parse_pairs,
    segment_diff_rules,
    unified_segments,
)
from app.services.normalize import (
    OPERATIONS as NORMALIZE_OPERATIONS,
    apply_operations_traced as normalize_apply_traced,
)
from app.services.structure_format import (
    OPERATIONS as SF_OPERATIONS,
    apply_operations_traced as sf_apply_traced,
)
from app.tasks.bulk_generation import generate_bulk_cell
from app.tasks.gdocs_import import run_gdocs_import
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
            "autotool_column_ids": table.autotool_column_ids,
            "gdocs_structure": table.gdocs_structure,
            "gdocs_slug_audit": table.gdocs_slug_audit,
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
                    "grounding_sources": c.grounding_sources,
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
            "autotool_column_ids": table.autotool_column_ids,
            "gdocs_structure": table.gdocs_structure,
            "gdocs_slug_audit": table.gdocs_slug_audit,
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
                    "grounding_sources": c.grounding_sources,
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
    # Direct subfolder count per folder (folders whose parent_id == id), so the
    # UI can show "N subfolders" on a folder card.
    subfolder_counts = dict(
        (
            await db.execute(
                select(BulkTableFolder.parent_id, func.count(BulkTableFolder.id))
                .where(BulkTableFolder.parent_id.is_not(None))
                .group_by(BulkTableFolder.parent_id)
            )
        ).all()
    )
    out: list[FolderRead] = []
    for f in rows:
        fr = FolderRead.model_validate(f)
        fr.table_count = int(counts.get(f.id, 0))
        fr.subfolder_count = int(subfolder_counts.get(f.id, 0))
        out.append(fr)
    return out


async def _would_create_folder_cycle(
    db: AsyncSession, folder_id: int, new_parent_id: int | None
) -> bool:
    """Walk up from new_parent_id; if we reach folder_id it's a cycle.

    Mirrors the domain-folder guard. ``seen`` also breaks out if the table
    somehow already held a cycle, so we never loop forever.
    """
    if new_parent_id is None:
        return False
    cursor: int | None = new_parent_id
    seen: set[int] = set()
    while cursor is not None:
        if cursor == folder_id:
            return True
        if cursor in seen:
            return True
        seen.add(cursor)
        cursor = (
            await db.execute(
                select(BulkTableFolder.parent_id).where(BulkTableFolder.id == cursor)
            )
        ).scalar_one_or_none()
    return False


@router.post(
    "/folders", response_model=FolderRead, status_code=status.HTTP_201_CREATED
)
async def create_folder(
    payload: FolderCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FolderRead:
    if payload.parent_id is not None:
        parent = await db.get(BulkTableFolder, payload.parent_id)
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Parent folder not found"
            )
    f = BulkTableFolder(
        name=payload.name.strip(),
        parent_id=payload.parent_id,
        created_by_id=actor.id,
    )
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
    # exclude_unset lets a PATCH touch just the name, just the parent, or both —
    # and distinguishes an omitted parent_id from an explicit null (→ top level).
    data = payload.model_dump(exclude_unset=True)

    if "parent_id" in data:
        new_parent = data["parent_id"]
        if new_parent is not None:
            if new_parent == folder_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A folder cannot be its own parent.",
                )
            if await db.get(BulkTableFolder, new_parent) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent folder not found",
                )
            if await _would_create_folder_cycle(db, folder_id, new_parent):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Move would create a cycle in the folder tree.",
                )
        f.parent_id = new_parent

    if data.get("name") is not None:
        f.name = data["name"].strip()

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
    # Also refuse when the folder still has subfolders — deleting it would
    # either orphan them (FK is RESTRICT, so the DB would block it anyway) or
    # silently strand their contents. Make the user empty it first.
    subfolders = (
        await db.execute(
            select(func.count(BulkTableFolder.id)).where(
                BulkTableFolder.parent_id == folder_id
            )
        )
    ).scalar_one()
    if int(subfolders) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Folder has {int(subfolders)} subfolder(s) in it. "
                "Move or delete them before deleting this folder."
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
    # Grounding only works on the Vertex Gemini path (the only place the Google
    # Search tool is wired). Reject it on any other provider — where it would
    # silently no-op — or on Claude, which can't ground. Raised before commit,
    # so the transaction rolls back and nothing persists.
    if col.grounding:
        if col.provider_code != "vertex":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Grounding requires this column's provider to be Google "
                    "Vertex AI with a Gemini model."
                ),
            )
        if (col.model or "").strip().lower().startswith("claude"):
            raise HTTPException(
                status_code=400,
                detail="Grounding is a Gemini feature — pick a Gemini model, not Claude.",
            )
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
        # Editing the source value invalidates any cached translations and
        # grounding provenance — otherwise the side-by-side translation panel
        # (or the sources list) would describe text that no longer exists.
        if cell.value != payload.value:
            if cell.translations is not None:
                cell.translations = None
            if cell.grounding_sources is not None:
                cell.grounding_sources = None
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
        text, code, model, pt, ct = await _translate_text(
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
        prompt_tokens=pt,
        completion_tokens=ct,
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

# Upload ceiling for a CSV import. The Traefik deployment sets no request-body
# limit, so this in-app guard is the only gate — keep it sane so an accidental
# giant upload fails with a clear 400 instead of spiking API memory.
_MAX_CSV_UPLOAD = 200 * 1024 * 1024  # 200 MB
# Cells per bulk INSERT statement — bounds statement + memory size on huge files.
_CSV_CELL_BATCH = 5000


@router.post(
    "/tables/import-csv", response_model=TableRead, status_code=status.HTTP_201_CREATED
)
async def import_csv(
    file: UploadFile = File(...),
    name: str = Form(...),
    delimiter: str = Form(","),
    has_header: bool = Form(True),
    folder_id: int | None = Form(None),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRead:
    """Create a bulk table from an uploaded CSV.

    Streamed multipart upload (not a JSON ``csv_text`` string) + bulk INSERTs
    (no per-row flush) so a multi-MB file imports in a couple of seconds instead
    of timing out the proxy (502). Empty cells are skipped; fields beyond the
    header count are ignored. ``folder_id`` lands the new table in a folder
    (same as a blank create) — omit for the implicit root.

    The parse + build is shared with the machine-to-machine ingest endpoint
    (``app/services/csv_import.py``); this route only adds auth, folder
    verification, and the paginated response.
    """
    from app.services.csv_import import CsvImportError, build_table_from_csv

    table_name = (name or "").strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="A table name is required.")
    if folder_id is not None:
        await _verify_folder(db, folder_id)

    try:
        t = await build_table_from_csv(
            db,
            name=table_name,
            raw=await file.read(),
            delimiter=delimiter,
            has_header=has_header,
            folder_id=folder_id,
            created_by_id=actor.id,
        )
    except CsvImportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    fresh = await _get_owned_table_or_404(db, t.id, actor, full=True)
    # The client only needs the id to navigate (the table page re-fetches), so
    # return a light first page instead of echoing every cell back as JSON.
    return await _table_to_read_paginated(db, fresh, 1, 25)


@router.get(
    "/tables/{table_id}/cells/{row_id}/{column_id}/cost",
    response_model=CellCostRead | None,
)
async def get_cell_generation_cost(
    table_id: int,
    row_id: int,
    column_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What generating this cell's CURRENT text cost, or ``null``.

    The LATEST ``bulk_cell`` usage event for the cell — so a regenerated cell
    reports the price of the text that's actually there rather than the sum of
    every discarded attempt. ``null`` means the cell was never AI-generated
    (hand-typed, imported, or produced before usage tracking existed).

    Note the event may carry ``cost_usd = None``: cost is computed at write time
    from the pricing table, so a provider:model with no configured rate is
    recorded unpriced — permanently, since rates are never applied
    retroactively. The caller shows "not priced" rather than "$0" in that case.
    """
    from app.db.models import UsageEvent

    await _get_table_or_404(db, table_id, actor, level="read")
    await _verify_cell_in_table(db, table_id, row_id, column_id)

    ev = (
        await db.execute(
            select(UsageEvent)
            .where(
                UsageEvent.source == "bulk_cell",
                UsageEvent.source_ref["row_id"].astext == str(row_id),
                UsageEvent.source_ref["column_id"].astext == str(column_id),
            )
            .order_by(UsageEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if ev is None:
        return None
    return CellCostRead(
        cost_usd=ev.cost_usd,
        provider_code=ev.provider_code,
        model=ev.model,
        prompt_tokens=ev.prompt_tokens,
        completion_tokens=ev.completion_tokens,
        generated_at=ev.created_at,
    )


def _build_tool_costs(
    rows: list[tuple[str, object, object, object, object, object]]
) -> list["ToolCostRead"]:
    """Shape ``(source, cost, prompt_tokens, completion_tokens, calls,
    unpriced)`` aggregate rows into the per-tool cost list, most-expensive
    first (source name as the tiebreaker). Pure (no DB) so it's unit-testable.
    """
    tools = [
        ToolCostRead(
            source=source,
            cost_usd=Decimal(cost or 0),
            prompt_tokens=int(pt or 0),
            completion_tokens=int(ct or 0),
            calls=int(calls or 0),
            unpriced_calls=int(unpriced or 0),
        )
        for (source, cost, pt, ct, calls, unpriced) in rows
    ]
    tools.sort(key=lambda tc: (-tc.cost_usd, tc.source))
    return tools


@router.get("/tables/{table_id}/cost", response_model=TableCostRead)
async def get_table_generation_cost(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableCostRead:
    """Total generation spend for a table, broken down by column.

    CUMULATIVE — every billed call, including retries and regenerations. That
    is deliberately different from the per-cell endpoint above, which reports
    only the latest attempt: this answers "what did this table cost me", the
    other answers "what is this text worth".

    One aggregate query rather than per-column round trips; ``source_ref``
    already carries ``table_id`` so no join back to rows/columns is needed for
    the numbers (only for column names).
    """
    from app.db.models import UsageEvent

    await _get_table_or_404(db, table_id, actor, level="read")

    col_id = UsageEvent.source_ref["column_id"].astext
    rows = (
        await db.execute(
            select(
                col_id.label("column_id"),
                func.coalesce(func.sum(UsageEvent.cost_usd), 0).label("cost"),
                func.coalesce(func.sum(UsageEvent.prompt_tokens), 0).label("pt"),
                func.coalesce(func.sum(UsageEvent.completion_tokens), 0).label("ct"),
                func.count().label("generations"),
                func.count(func.distinct(UsageEvent.source_ref["row_id"].astext)).label(
                    "cells"
                ),
                func.count()
                .filter(UsageEvent.cost_usd.is_(None))
                .label("unpriced"),
            )
            .where(
                UsageEvent.source == "bulk_cell",
                UsageEvent.source_ref["table_id"].astext == str(table_id),
            )
            .group_by(col_id)
        )
    ).all()

    # Column names for the breakdown. Columns deleted since generation keep
    # their spend (it was really spent) under a placeholder name.
    names = {
        c.id: c.name
        for c in (
            await db.execute(
                select(BulkTableColumn).where(BulkTableColumn.table_id == table_id)
            )
        )
        .scalars()
        .all()
    }

    breakdown: list[ColumnCostRead] = []
    for r in rows:
        try:
            cid = int(r.column_id)
        except (TypeError, ValueError):
            continue
        breakdown.append(
            ColumnCostRead(
                column_id=cid,
                column_name=names.get(cid, f"(deleted column #{cid})"),
                cost_usd=Decimal(r.cost),
                prompt_tokens=int(r.pt),
                completion_tokens=int(r.ct),
                generations=int(r.generations),
                cells=int(r.cells),
                unpriced_generations=int(r.unpriced),
            )
        )
    breakdown.sort(key=lambda c: (-c.cost_usd, c.column_name))

    # AI mini-tool spend for this table (translate, AI link-fix). Same
    # usage_events store, but a different `source` than bulk_cell and keyed to
    # the table via source_ref. One row per tool. Older events recorded no
    # tokens (cost NULL) — surfaced as unpriced_calls so a $0 line reads as
    # "ran before cost tracking", not "free".
    tool_rows = (
        await db.execute(
            select(
                UsageEvent.source.label("source"),
                func.coalesce(func.sum(UsageEvent.cost_usd), 0).label("cost"),
                func.coalesce(func.sum(UsageEvent.prompt_tokens), 0).label("pt"),
                func.coalesce(func.sum(UsageEvent.completion_tokens), 0).label("ct"),
                func.count().label("calls"),
                func.count().filter(UsageEvent.cost_usd.is_(None)).label("unpriced"),
            )
            .where(
                UsageEvent.source.in_(("brain_translate", "brain_fix_links")),
                UsageEvent.source_ref["table_id"].astext == str(table_id),
            )
            .group_by(UsageEvent.source)
        )
    ).all()
    tools = _build_tool_costs(
        [
            (r.source, r.cost, r.pt, r.ct, r.calls, r.unpriced)
            for r in tool_rows
        ]
    )

    return TableCostRead(
        table_id=table_id,
        cost_usd=sum((c.cost_usd for c in breakdown), Decimal(0)),
        prompt_tokens=sum(c.prompt_tokens for c in breakdown),
        completion_tokens=sum(c.completion_tokens for c in breakdown),
        generations=sum(c.generations for c in breakdown),
        cells=sum(c.cells for c in breakdown),
        unpriced_generations=sum(c.unpriced_generations for c in breakdown),
        columns=breakdown,
        tools=tools,
    )


def _build_gen_health(
    table_id: int, rows: list[tuple[int, str, int, int]]
) -> TableGenHealthRead:
    """Shape ``(column_id, name, failed, truncated)`` aggregate rows into the
    response: drop columns with no problem, order most-affected first, and roll
    up the table totals. Pure (no DB) so it's unit-testable on its own."""
    breakdown = [
        ColumnGenHealthRead(
            column_id=cid, column_name=name, failed=failed, truncated=truncated
        )
        for (cid, name, failed, truncated) in rows
        if failed or truncated
    ]
    # Most-affected first, name as the tiebreaker for a stable order. Failed and
    # truncated both count toward the rank; the UI splits them back out per row.
    breakdown.sort(key=lambda c: (-(c.failed + c.truncated), c.column_name))
    return TableGenHealthRead(
        table_id=table_id,
        failed=sum(c.failed for c in breakdown),
        truncated=sum(c.truncated for c in breakdown),
        columns=breakdown,
    )


@router.get("/tables/{table_id}/gen-health", response_model=TableGenHealthRead)
async def get_table_gen_health(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableGenHealthRead:
    """Which columns hold cells the operator can retry, and how many.

    Two disjoint problems, matching the grid's two retry modes:
      * ``failed``    — status='failed'; the request itself errored.
      * ``truncated`` — a truncation finish_reason; the reply hit the output
        ceiling and the kept text is a partial (status stays 'generated').
    A failed cell has its finish_reason cleared, so the two never overlap.

    Whole-table, not the current page: the grid paginates cells, so the banner
    can't count these from what's on screen. One indexed aggregate over the
    cells (joined to columns for the table filter + names), same shape as the
    cost endpoint above.
    """
    from app.providers.base import TRUNCATION_FINISH_REASONS

    await _get_table_or_404(db, table_id, actor, level="read")

    is_failed = case((BulkTableCell.status == "failed", 1), else_=0)
    is_truncated = case(
        (
            func.lower(BulkTableCell.finish_reason).in_(
                sorted(TRUNCATION_FINISH_REASONS)
            ),
            1,
        ),
        else_=0,
    )
    rows = (
        await db.execute(
            select(
                BulkTableColumn.id.label("column_id"),
                BulkTableColumn.name.label("column_name"),
                func.coalesce(func.sum(is_failed), 0).label("failed"),
                func.coalesce(func.sum(is_truncated), 0).label("truncated"),
            )
            .select_from(BulkTableCell)
            .join(BulkTableColumn, BulkTableColumn.id == BulkTableCell.column_id)
            .where(BulkTableColumn.table_id == table_id)
            .group_by(BulkTableColumn.id, BulkTableColumn.name)
        )
    ).all()

    return _build_gen_health(
        table_id,
        [
            (int(r.column_id), r.column_name, int(r.failed), int(r.truncated))
            for r in rows
        ],
    )


# ---------- public cell share links ----------


async def _verify_cell_in_table(
    db: AsyncSession, table_id: int, row_id: int, column_id: int
) -> tuple[BulkTableRow, BulkTableColumn]:
    """Load the row + column, asserting BOTH belong to ``table_id``.

    Load-bearing for security: without it, a user with access to table A could
    mint a PUBLIC link for a cell in table B just by passing its ids.
    """
    row = (
        await db.execute(
            select(BulkTableRow).where(
                BulkTableRow.id == row_id, BulkTableRow.table_id == table_id
            )
        )
    ).scalar_one_or_none()
    col = (
        await db.execute(
            select(BulkTableColumn).where(
                BulkTableColumn.id == column_id,
                BulkTableColumn.table_id == table_id,
            )
        )
    ).scalar_one_or_none()
    if row is None or col is None:
        raise HTTPException(status_code=404, detail="Cell not found in this table.")
    return row, col


async def _active_share_link(
    db: AsyncSession, table_id: int, row_id: int, column_id: int
) -> "CellShareLink | None":
    from app.db.models import CellShareLink

    now = datetime.now(timezone.utc)
    return (
        await db.execute(
            select(CellShareLink)
            .where(
                CellShareLink.table_id == table_id,
                CellShareLink.row_id == row_id,
                CellShareLink.column_id == column_id,
                CellShareLink.revoked_at.is_(None),
                CellShareLink.expires_at > now,
            )
            .order_by(CellShareLink.id.desc())
        )
    ).scalars().first()


@router.get(
    "/tables/{table_id}/cells/{row_id}/{column_id}/share",
    response_model=ShareLinkRead | None,
)
async def get_cell_share_link(
    table_id: int,
    row_id: int,
    column_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The cell's active share link, or ``null`` when it isn't shared — lets the
    cell editor show "already shared" without creating one as a side effect."""
    await _get_table_or_404(db, table_id, actor, level="read")
    await _verify_cell_in_table(db, table_id, row_id, column_id)
    return await _active_share_link(db, table_id, row_id, column_id)


@router.post(
    "/tables/{table_id}/cells/{row_id}/{column_id}/share",
    response_model=ShareLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_cell_share_link(
    table_id: int,
    row_id: int,
    column_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mint (or re-use) a public read-only link to this cell's preview.

    Idempotent: while an active link exists, sharing again returns the SAME URL
    rather than littering the table with tokens. Requires WRITE access — putting
    content on a public URL is a publishing action, not a read.

    The link is LIVE (renders the cell's current value) and expires after
    ``SHARE_LINK_TTL_DAYS``; ``DELETE`` revokes it sooner.
    """
    import secrets
    from datetime import timedelta

    from app.db.models import CellShareLink
    from app.db.models.cell_share_link import SHARE_LINK_TTL_DAYS

    await _get_table_or_404(db, table_id, actor, level="write")
    await _verify_cell_in_table(db, table_id, row_id, column_id)

    existing = await _active_share_link(db, table_id, row_id, column_id)
    if existing is not None:
        return existing

    link = CellShareLink(
        token=secrets.token_urlsafe(32),
        table_id=table_id,
        row_id=row_id,
        column_id=column_id,
        created_by_id=actor.id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=SHARE_LINK_TTL_DAYS),
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


@router.delete("/share-links/{link_id}", status_code=204, response_class=Response)
async def revoke_cell_share_link(
    link_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke a share link immediately (the public URL 404s from here on).

    Kept as a soft revoke rather than a delete so the row survives as an audit
    trail of what was once public."""
    from app.db.models import CellShareLink

    link = await db.get(CellShareLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    await _get_table_or_404(db, link.table_id, actor, level="write")
    if link.revoked_at is None:
        link.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return Response(status_code=204)


async def _apply_cell_update(
    db: AsyncSession,
    table_id: int,
    *,
    rows: list[list[str | None]],
    mappings: list[tuple[int, int]],
    match_mode: str,
    source_key_index: int | None,
    key_column_id: int | None,
    case_insensitive_key: bool,
    skip_empty: bool,
) -> TableUpdateResult:
    """Shared core for both update endpoints (JSON paste + multipart file).

    ``mappings`` is a list of ``(source_index, column_id)``. Matches each
    incoming row to existing table rows — by a key column or by row order —
    then bulk-upserts the mapped cells. Rows that match nothing are ignored
    (never adds/removes rows). The upsert drops any cached translation on the
    touched cells (same invariant as the editor path).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    if match_mode not in ("key", "order"):
        raise HTTPException(status_code=400, detail="Bad match_mode.")
    if not mappings:
        raise HTTPException(status_code=400, detail="No columns mapped.")

    table_col_ids = {
        cid
        for (cid,) in (
            await db.execute(
                select(BulkTableColumn.id).where(
                    BulkTableColumn.table_id == table_id
                )
            )
        ).all()
    }
    bad = {cid for (_si, cid) in mappings} - table_col_ids
    if bad:
        raise HTTPException(
            status_code=400, detail=f"Unknown column id(s): {sorted(bad)}"
        )
    if match_mode == "key":
        if source_key_index is None or key_column_id is None:
            raise HTTPException(
                status_code=400,
                detail="Key matching needs a source key column and a table key column.",
            )
        if key_column_id not in table_col_ids:
            raise HTTPException(status_code=400, detail="Unknown key column id.")

    def cell_value(row: list[str | None], idx: int) -> str | None:
        if idx < 0 or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        v = v.strip()
        return v or None

    # (row_id, column_id) -> value. A dict so a later incoming row that targets
    # the same cell simply wins (last-write-wins, deterministic).
    writes: dict[tuple[int, int], str | None] = {}
    matched_rows = 0
    unmatched_rows = 0

    if match_mode == "order":
        table_row_ids = [
            rid
            for (rid,) in (
                await db.execute(
                    select(BulkTableRow.id)
                    .where(BulkTableRow.table_id == table_id)
                    .order_by(BulkTableRow.position, BulkTableRow.id)
                )
            ).all()
        ]
        n = len(table_row_ids)
        for i, row in enumerate(rows):
            if i >= n:
                unmatched_rows += 1
                continue
            rid = table_row_ids[i]
            matched_rows += 1
            for src, col in mappings:
                v = cell_value(row, src)
                if v is None and skip_empty:
                    continue
                writes[(rid, col)] = v
    else:
        def norm_key(s: str | None) -> str | None:
            if s is None:
                return None
            s = s.strip()
            if not s:
                return None
            return s.lower() if case_insensitive_key else s

        key_rows = (
            await db.execute(
                select(BulkTableCell.row_id, BulkTableCell.value).where(
                    BulkTableCell.column_id == key_column_id
                )
            )
        ).all()
        index: dict[str, list[int]] = {}
        for rid, val in key_rows:
            k = norm_key(val)
            if k is None:
                continue
            index.setdefault(k, []).append(rid)

        for row in rows:
            k = norm_key(cell_value(row, source_key_index))
            rids = index.get(k) if k is not None else None
            if not rids:
                unmatched_rows += 1
                continue
            matched_rows += 1
            for rid in rids:
                for src, col in mappings:
                    v = cell_value(row, src)
                    if v is None and skip_empty:
                        continue
                    writes[(rid, col)] = v

    # Drop no-op writes: a cell whose incoming value already equals what's
    # stored isn't a real change, so it shouldn't be written or counted. This
    # is what keeps mapping the key column onto itself (same value) from
    # inflating "cells updated".
    if writes:
        rids = {r for (r, _c) in writes}
        cids = {c for (_r, c) in writes}
        existing = {
            (r, c): val
            for r, c, val in (
                await db.execute(
                    select(
                        BulkTableCell.row_id,
                        BulkTableCell.column_id,
                        BulkTableCell.value,
                    ).where(
                        BulkTableCell.row_id.in_(rids),
                        BulkTableCell.column_id.in_(cids),
                    )
                )
            ).all()
        }
        writes = {
            (r, c): nv
            for (r, c), nv in writes.items()
            if nv != existing.get((r, c))
        }

    if writes:
        rows_payload = [
            {
                "row_id": rid,
                "column_id": cid,
                "value": v,
                "status": "manual" if v else "empty",
            }
            for (rid, cid), v in writes.items()
        ]
        for i in range(0, len(rows_payload), _CSV_CELL_BATCH):
            chunk = rows_payload[i : i + _CSV_CELL_BATCH]
            stmt = pg_insert(BulkTableCell).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_bulk_cells_row_column",
                set_={
                    "value": stmt.excluded.value,
                    "status": stmt.excluded.status,
                    "translations": None,
                    "error": None,
                },
            )
            await db.execute(stmt)
        await _bump_table_updated(db, table_id)
        await db.commit()

    return TableUpdateResult(
        matched_rows=matched_rows,
        unmatched_rows=unmatched_rows,
        updated_cells=len(writes),
        affected_table_rows=len({rid for (rid, _cid) in writes}),
    )


@router.post(
    "/tables/{table_id}/update-cells", response_model=TableUpdateResult
)
async def update_cells_from_rows(
    table_id: int,
    payload: TableUpdateRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableUpdateResult:
    """Patch an existing table's cells from pasted rows (small JSON payload).
    File uploads go through ``/update-cells-csv`` so a large CSV streams as
    multipart instead of inflating a JSON body."""
    await _get_table_or_404(db, table_id, actor, level="write")
    return await _apply_cell_update(
        db,
        table_id,
        rows=payload.rows,
        mappings=[(m.source_index, m.column_id) for m in payload.mappings],
        match_mode=payload.match_mode,
        source_key_index=payload.source_key_index,
        key_column_id=payload.key_column_id,
        case_insensitive_key=payload.case_insensitive_key,
        skip_empty=payload.skip_empty,
    )


@router.post(
    "/tables/{table_id}/update-cells-csv", response_model=TableUpdateResult
)
async def update_cells_from_csv(
    table_id: int,
    file: UploadFile = File(...),
    delimiter: str = Form(","),
    has_header: bool = Form(True),
    mappings: str = Form(...),  # JSON: [{"source_index": int, "column_id": int}]
    match_mode: str = Form(...),
    source_key_index: int | None = Form(None),
    key_column_id: int | None = Form(None),
    case_insensitive_key: bool = Form(False),
    skip_empty: bool = Form(True),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableUpdateResult:
    """Patch an existing table from an uploaded CSV. Streamed multipart +
    server-side parse — same 100 MB ceiling and robust CSV handling as the
    create-table import, so a re-uploaded export updates in place without
    inflating a JSON request or hitting the paste row cap."""
    await _get_table_or_404(db, table_id, actor, level="write")

    delim = "\t" if delimiter in ("\\t", "\t") else delimiter
    if len(delim) != 1:
        raise HTTPException(
            status_code=400, detail="Delimiter must be a single character."
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > _MAX_CSV_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {_MAX_CSV_UPLOAD // (1024 * 1024)} MB).",
        )
    try:
        text_data = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text_data = raw.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="The file is not valid text.")

    parsed_rows = [r for r in csv.reader(io.StringIO(text_data), delimiter=delim)]
    if has_header and parsed_rows:
        parsed_rows = parsed_rows[1:]

    try:
        maps = [
            (int(m["source_index"]), int(m["column_id"]))
            for m in json.loads(mappings)
        ]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Bad mappings payload.")

    return await _apply_cell_update(
        db,
        table_id,
        rows=parsed_rows,  # type: ignore[arg-type]
        mappings=maps,
        match_mode=match_mode,
        source_key_index=source_key_index,
        key_column_id=key_column_id,
        case_insensitive_key=case_insensitive_key,
        skip_empty=skip_empty,
    )


# ---------- Google-Docs import ----------

_MAX_GDOCS_UPLOAD = 200 * 1024 * 1024  # 200 MB — Doc HTML + JSON export adds up


async def _get_gdocs_run_or_404(
    db: AsyncSession, run_id: int
) -> GdocsImportRun:
    run = await db.get(GdocsImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Import run not found")
    return run


@router.post(
    "/import/gdocs",
    response_model=GdocsImportRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_gdocs(
    file: UploadFile = File(...),
    name: str = Form(...),
    folder_id: int | None = Form(None),
    provider_code: str | None = Form(None),
    model: str | None = Form(None),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GdocsImportRun:
    """Upload an Apps-Script JSON export and queue a background import (202).

    The job cleans every linked Doc, extracts meta, pairs each Structure page
    to a Doc, and builds a Custom-CMS-shaped bulk table (single/multi by
    distinct domain count). ``provider_code``/``model`` optionally pin which AI
    runs the meta + pairing steps; left blank, the job uses the first-enabled
    provider and its default model. Poll ``GET /library/import/gdocs-runs/{id}``.
    """
    table_name = (name or "").strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="A table name is required.")

    # Resolve the optional AI override up-front so a bad pick fails the upload
    # (clear 400) instead of the background job (a silent 'failed' run later).
    provider_code = (provider_code or "").strip() or None
    model = (model or "").strip() or None
    if model and not provider_code:
        raise HTTPException(
            status_code=400, detail="Pick a provider before choosing a model."
        )
    if provider_code:
        snapshot = await get_enabled_providers(db)
        chosen = next((p for p in snapshot if p.code == provider_code), None)
        if chosen is None:
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{provider_code}' is not enabled.",
            )
        if not chosen.has_api_key:
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{provider_code}' has no API key configured.",
            )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > _MAX_GDOCS_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {_MAX_GDOCS_UPLOAD // (1024 * 1024)} MB).",
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=400, detail="The file is not valid JSON."
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise HTTPException(
            status_code=400,
            detail="Unexpected file shape — expected the Apps Script JSON "
            "with a 'rows' array.",
        )
    if not isinstance(payload.get("docs"), dict):
        payload["docs"] = {}

    if folder_id is not None:
        folder = await db.get(BulkTableFolder, folder_id)
        if folder is None:
            raise HTTPException(status_code=404, detail="Folder not found")

    run = GdocsImportRun(
        status="queued",
        table_name=table_name,
        target_folder_id=folder_id,
        provider_code=provider_code,
        model=model,
        payload=payload,
        created_by_id=actor.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    run_gdocs_import.delay(run.id)
    return run


@router.get("/import/gdocs-runs", response_model=list[GdocsImportRunRead])
async def list_gdocs_runs(
    limit: int = Query(default=50, ge=1, le=200),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GdocsImportRun]:
    """Import history, newest first (all users — this is an internal tool)."""
    runs = (
        (
            await db.execute(
                select(GdocsImportRun)
                .order_by(GdocsImportRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(runs)


@router.get("/import/gdocs-runs/{run_id}", response_model=GdocsImportRunRead)
async def get_gdocs_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GdocsImportRun:
    """Run state + progress counters + warnings. The progress page polls this
    every ~2s while active, then stops on a terminal status."""
    return await _get_gdocs_run_or_404(db, run_id)


@router.post(
    "/import/gdocs-runs/{run_id}/cancel", response_model=GdocsImportRunRead
)
async def cancel_gdocs_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GdocsImportRun:
    """Request cancellation; the worker observes it between chunks."""
    run = await _get_gdocs_run_or_404(db, run_id)
    if run.status in ("queued", "running"):
        run.status = "cancelled"
        await db.commit()
        await db.refresh(run)
    return run


@router.delete(
    "/import/gdocs-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_gdocs_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an import run from history. Only terminal runs can be removed —
    an active run must be cancelled first (deleting the row mid-job would
    orphan the worker, which writes to it). This removes only the history
    record; the bulk table the run built (if any) is independent and kept."""
    run = await _get_gdocs_run_or_404(db, run_id)
    if run.status in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="Cancel the import before deleting it.",
        )
    await db.delete(run)
    await db.commit()


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


def _missing_mapped_vars(template: str, variable_map: dict | None) -> list[str]:
    """Prompt variables in ``template`` that ``variable_map`` doesn't fill.

    A variable is 'set' when the map holds a truthy source-column id for it;
    absent or null counts as unmapped. Pure (no DB) so it's unit-testable."""
    from app.services.prompts import extract_variables

    vmap = variable_map or {}
    return [v for v in extract_variables(template) if not vmap.get(v)]


async def _columns_missing_variables(
    db: AsyncSession, cols: list[BulkTableColumn]
) -> list[UnmappedColumn]:
    """Which of ``cols`` would generate against unfilled {{placeholders}} —
    their prompt has variables ``variable_map`` doesn't cover. Callers block the
    run on a non-empty result so AI spend isn't wasted on broken prompts."""
    from app.services.bulk_generation import _resolve_prompt_template

    out: list[UnmappedColumn] = []
    for col in cols:
        try:
            template = await _resolve_prompt_template(
                db, col.prompt_id, col.prompt_version_number
            )
        except ValueError:
            out.append(
                UnmappedColumn(
                    column_id=col.id, name=col.name, missing=["(prompt unavailable)"]
                )
            )
            continue
        missing = _missing_mapped_vars(template, col.variable_map)
        if missing:
            out.append(
                UnmappedColumn(column_id=col.id, name=col.name, missing=missing)
            )
    return out


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
                # Truncated cells are status='generated' (the partial text is
                # kept and usable), so neither 'empty' nor 'failed' matches
                # them and only 'all' would — which would also redo every
                # complete cell. This mode targets exactly the cut-off ones.
                or (
                    effective_mode == "truncated"
                    and existing is not None
                    and existing.truncated
                )
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
    unmapped = await _columns_missing_variables(db, cols)
    rows = await _resolve_generation_rows(db, table_id, payload)
    if not rows:
        return GeneratePreviewResponse(
            will_generate=0, skipped=0, unmapped_columns=unmapped
        )
    to_enqueue, skipped = await _resolve_generation_candidates(
        db, table_id, cols, rows, payload
    )
    return GeneratePreviewResponse(
        will_generate=len(to_enqueue), skipped=skipped, unmapped_columns=unmapped
    )


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

    # Block the run if any target column's prompt has unmapped variables:
    # generating those burns AI calls on prompts with literal {{placeholders}}
    # left in. The queue modal surfaces the same list via /generate-preview.
    unmapped = await _columns_missing_variables(db, cols)
    if unmapped:
        names = ", ".join(u.name for u in unmapped)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Can't generate: these columns have unmapped prompt variables "
                f"— {names}. Map every variable to a column first."
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

    mode_label = {
        "empty": "empty",
        "failed": "failed",
        "truncated": "truncated",
        "all": "all",
    }[effective_mode]
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
    # Persist the status flip before the guarded settles below read it back.
    await db.flush()

    # Settle cells that were still 'generating' when Cancel was clicked. Their
    # tasks may never run (a lost broker message / OOM-killed worker strands the
    # cell) or may be mid-flight; flipping them here stops the grid spinning the
    # instant Cancel lands, instead of waiting up to 20 min for the watchdog.
    # Status-guarded and count-what-we-flip: a queued task that later hits its
    # own (also guarded) cancel pre-check can't move the same cell, so `skipped`
    # is bumped exactly once per cell. Matches the pre-check's convention —
    # cell -> 'failed', counter -> skipped.
    swept = (
        (
            await db.execute(
                update(BulkTableCell)
                .where(
                    BulkTableCell.generation_run_id == run_id,
                    BulkTableCell.status == "generating",
                )
                .values(
                    status="failed",
                    error="Cancelled before completion",
                    finish_reason=None,
                )
                .returning(BulkTableCell.id)
            )
        )
        .scalars()
        .all()
    )
    if swept:
        await db.execute(
            text(
                "UPDATE bulk_generation_runs "
                "SET skipped = skipped + :n WHERE id = :id"
            ),
            {"n": len(swept), "id": run_id},
        )
    # If that drained the run (nothing left in flight), stamp finished_at so the
    # UI stops showing it as ongoing. Mirrors _bump_run_counter's cancelled
    # branch; the last live worker stamps it otherwise.
    await db.execute(
        text(
            "UPDATE bulk_generation_runs SET finished_at = NOW() "
            "WHERE id = :id AND status = 'cancelled' AND finished_at IS NULL "
            "  AND done + failed + skipped >= total"
        ),
        {"id": run_id},
    )
    await db.commit()
    await db.refresh(run)
    return run


# How long a run must have been silent before "Recover now" treats its
# in-flight cells as dead. Far shorter than the watchdog's 20-min stall timer
# (the operator is asserting it's stuck), but non-zero so a run that produced a
# cell in the last couple of minutes — i.e. workers are alive — is left alone
# instead of having live work culled.
_RECOVER_GRACE_MINUTES = 2.0


@router.post("/gen-runs/{run_id}/recover", response_model=BulkGenerationRunRead)
async def recover_gen_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkGenerationRun:
    """Operator override for a run that looks frozen: run the watchdog's
    reconcile right now instead of waiting out its 20-minute stall timer.

    Flips cells wedged on 'generating' to 'failed' (retry them with "Only
    failed cells") and settles the run. Guarded by a short no-progress window:
    if the run produced a cell within the last couple of minutes it's still
    alive, so this is a no-op and returns the run untouched. No-op on terminal
    (done / failed) runs.
    """
    run = await _get_gen_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")

    if run.status in ("done", "failed"):
        return run

    # Reuse the watchdog's reconcile, but with a short window so it acts now.
    from app.tasks.bulk_generation import _reconcile_run

    await _reconcile_run(db, run_id, no_progress_minutes=_RECOVER_GRACE_MINUTES)
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


async def _get_normalize_run_or_404(
    db: AsyncSession, run_id: int
) -> NormalizeRun:
    run = await db.get(NormalizeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Normalize run not found")
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
        finds = parse_finds(payload.pattern)
        rules = compile_rules(
            finds,
            [""] * len(finds),
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
        n = count_matches_rules(rules, cell.value, whole_cell=payload.whole_cell)
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
        finds, replaces = parse_pairs(payload.pattern, payload.replacement)
        rules = compile_rules(
            finds,
            replaces,
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
        new_value, n = apply_rules(
            rules,
            cell.value,
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

    # Recompile the run's find→replace pairs once to recover per-cell match
    # spans for the before/after highlight. If they somehow no longer compile,
    # fall back to whole-value segments (no highlight) rather than failing.
    rules = None
    try:
        finds, replaces = parse_pairs(run.pattern, run.replacement)
        rules = compile_rules(
            finds,
            replaces,
            is_regex=run.is_regex,
            case_sensitive=run.case_sensitive,
        )
    except InvalidPattern:
        rules = None

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
        # new side both come from the rule match spans.
        if rules is not None and old_v is not None:
            old_segs, replace_new_segs = segment_diff_rules(
                rules,
                old_v,
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


# ---------- Normalize (content tool) ----------


def _normalize_ops_ordered(operations: list[str]) -> list[str]:
    """Selection as a subset of the canonical OPERATIONS, in canonical order."""
    chosen = set(operations)
    return [op for op in NORMALIZE_OPERATIONS if op in chosen]


@router.post(
    "/tables/{table_id}/normalize/preview",
    response_model=NormalizePreview,
)
async def preview_normalize(
    table_id: int,
    payload: NormalizePreviewRequest,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NormalizePreview:
    """Dry run: counts how many cells in scope WOULD change and returns a
    paginated sample with the before/after diff. Persists nothing."""
    await _get_table_or_404(db, table_id, actor, level="read")
    ops = _normalize_ops_ordered(payload.operations)
    if not ops:
        raise HTTPException(
            status_code=400, detail="Select at least one operation."
        )

    candidates = 0
    changed: list[tuple[BulkTableCell, int, str, str, list[str]]] = []
    for cell, row_pos, col_name in await _load_cells_with_meta(
        db, table_id, payload.column_ids
    ):
        if not cell.value:
            continue
        candidates += 1
        new_value, applied = normalize_apply_traced(cell.value, ops)
        if applied and new_value != cell.value:
            changed.append((cell, row_pos, col_name, new_value, applied))

    start = (page - 1) * page_size
    page_items = changed[start : start + page_size]
    items: list[NormalizePreviewCell] = []
    for cell, row_pos, col_name, new_value, applied in page_items:
        old_segs, new_segs = diff_segments(cell.value or "", new_value)
        items.append(
            NormalizePreviewCell(
                row_id=cell.row_id,
                row_position=row_pos,
                column_id=cell.column_id,
                column_name=col_name,
                old_value=cell.value,
                new_value=new_value,
                applied_ops=applied,
                old_segments=old_segs,  # type: ignore[arg-type]
                new_segments=new_segs,  # type: ignore[arg-type]
            )
        )
    return NormalizePreview(
        candidates=candidates,
        would_change=len(changed),
        page=page,
        page_size=page_size,
        items=items,
    )


@router.post(
    "/tables/{table_id}/normalize",
    response_model=NormalizeRunRead,
    status_code=status.HTTP_201_CREATED,
)
async def normalize_table(
    table_id: int,
    payload: NormalizeApplyRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NormalizeRun:
    """Apply the selected transforms across EVERY cell in scope at once and
    record a revertable run with a full before/after snapshot. 400 when nothing
    would change (no empty run is created)."""
    await _get_table_or_404(db, table_id, actor, level="write")
    ops = _normalize_ops_ordered(payload.operations)
    if not ops:
        raise HTTPException(
            status_code=400, detail="Select at least one operation."
        )

    snapshot: list[dict] = []
    for cell, _row_pos, _col_name in await _load_cells_with_meta(
        db, table_id, payload.column_ids
    ):
        if not cell.value:
            continue
        new_value, applied = normalize_apply_traced(cell.value, ops)
        if applied and new_value != cell.value:
            snapshot.append(
                {
                    "row_id": cell.row_id,
                    "column_id": cell.column_id,
                    "old_value": cell.value,
                    "old_status": cell.status,
                    "new_value": new_value,
                }
            )
            # A targeted normalize isn't a regeneration: keep the cell's status
            # but drop any cached translation — it no longer matches the source,
            # same invariant the upsert path enforces.
            cell.value = new_value
            if cell.translations is not None:
                cell.translations = None

    if not snapshot:
        raise HTTPException(
            status_code=400, detail="Nothing to normalize — cells already clean."
        )

    run = NormalizeRun(
        table_id=table_id,
        operations=ops,
        column_ids=list(payload.column_ids),
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
    "/tables/{table_id}/normalize-runs",
    response_model=list[NormalizeRunRead],
)
async def list_normalize_runs(
    table_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NormalizeRun]:
    """Normalize history for a table, newest first."""
    await _get_table_or_404(db, table_id, actor, level="read")
    runs = (
        (
            await db.execute(
                select(NormalizeRun)
                .where(NormalizeRun.table_id == table_id)
                .order_by(NormalizeRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(runs)


@router.get("/normalize-runs/{run_id}", response_model=NormalizeRunDetail)
async def get_normalize_run(
    run_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    op: str | None = Query(default=None),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NormalizeRunDetail:
    """Run metadata + the affected cells (paginated) with before/after and a
    per-cell ``drifted`` flag (current value no longer matches what the
    normalize wrote). ``drifted_count`` is computed across the whole run.
    ``op`` filters to cells where that transform actually applied."""
    run = await _get_normalize_run_or_404(db, run_id)
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

    ops = run.operations or []
    # Optional filter: only cells where the chosen transform actually applied.
    # The snapshot stores no per-cell applied_ops (it's recomputed from the
    # stored old value), so filtering recomputes it for each entry — cheap
    # in-memory string ops, same call the page loop uses below.
    op_filter = op if op in NORMALIZE_OPERATIONS else None
    if op_filter:
        visible = [
            e
            for e in snap
            if op_filter
            in normalize_apply_traced(e["old_value"] or "", ops)[1]
        ]
    else:
        visible = snap

    start = (page - 1) * page_size
    page_snap = visible[start : start + page_size]
    items: list[NormalizedCell] = []
    for e in page_snap:
        c = cur.get((e["row_id"], e["column_id"]))
        cur_val = c.value if c is not None else None
        cur_status = c.status if c is not None else "empty"
        old_v = e["old_value"]
        new_v = e["new_value"]
        drifted = cur_val != new_v
        # Which transforms actually changed THIS cell (recomputed from the
        # stored old value — cheap + deterministic).
        _nv, applied = normalize_apply_traced(old_v or "", ops)
        # old side (struck removals) + the green "what normalize produced" new
        # side both come from a char-level diff of old vs new.
        old_segs, normalize_new_segs = diff_segments(old_v or "", new_v or "")
        # When the cell was edited after the normalize, the "after" column
        # shows the LIVE value with the later edit highlighted (amber), diffed
        # against what the normalize wrote. Otherwise it shows the normalize
        # result with the inserted text highlighted (green).
        if drifted:
            new_segs = (
                drift_segments(new_v or "", cur_val)
                if cur_val is not None
                else []
            )
        else:
            new_segs = normalize_new_segs
        items.append(
            NormalizedCell(
                row_id=e["row_id"],
                row_position=row_pos.get(e["row_id"], 0),
                column_id=e["column_id"],
                column_name=col_name.get(e["column_id"], "—"),
                old_value=old_v,
                new_value=new_v,
                current_value=cur_val,
                current_status=cur_status,  # type: ignore[arg-type]
                drifted=drifted,
                applied_ops=applied,
                old_segments=old_segs,  # type: ignore[arg-type]
                new_segments=new_segs,  # type: ignore[arg-type]
            )
        )

    return NormalizeRunDetail(
        id=run.id,
        table_id=run.table_id,
        name=run.name,
        operations=run.operations,
        column_ids=run.column_ids,
        cell_count=run.cell_count,
        status=run.status,  # type: ignore[arg-type]
        created_by_id=run.created_by_id,
        created_at=run.created_at,
        reverted_at=run.reverted_at,
        created_by_name=await _resolve_creator_name(db, run.created_by_id),
        page=page,
        page_size=page_size,
        total_cells=len(visible),
        drifted_count=drifted_count,
        items=items,
    )


@router.post("/normalize-runs/{run_id}/revert", response_model=NormalizeRunRead)
async def revert_normalize_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NormalizeRun:
    """Restore every cell this run changed to its pre-normalize value. Writes
    through the normal cell path (clears stale translations). Idempotent:
    a no-op on an already-reverted run. Note this discards any edits made
    to those cells after the normalize — the run page surfaces a drift count
    so the operator knows before clicking."""
    run = await _get_normalize_run_or_404(db, run_id)
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


@router.patch("/normalize-runs/{run_id}", response_model=NormalizeRunRead)
async def rename_normalize_run(
    run_id: int,
    payload: RunRename,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NormalizeRun:
    run = await _get_normalize_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    run.name = _norm_run_name(payload)
    await db.commit()
    await db.refresh(run)
    return run


@router.delete(
    "/normalize-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_normalize_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    run = await _get_normalize_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    await db.delete(run)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        # Optional link-type classification (product / internal / external).
        from app.services.translation_links import parse_domains

        product_domains = parse_domains(payload.product_domain)
        domain_col_ids = list(payload.internal_domain_column_ids)
        if domain_col_ids:
            await _verify_columns_in_table(db, table_id, domain_col_ids)
        classify_config = (
            {
                "product_domains": product_domains,
                "internal_domain_column_ids": domain_col_ids,
            }
            if (product_domains or domain_col_ids)
            else None
        )
        run = LinkCheckRun(
            table_id=table_id,
            created_by_id=actor.id,
            status="queued",
            column_ids=list(payload.column_ids),
            expected_column_ids=list(payload.expected_column_ids),
            check_juxtapose=payload.check_juxtapose,
            check_crawl=payload.check_crawl,
            include_ok=payload.include_ok,
            classify_config=classify_config,
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
    from app.services.translation_links import (
        parse_default_langs,
        parse_domains,
        parse_exceptions,
    )

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
        "product_default_langs": parse_default_langs(cfg.product_default_langs),
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
    link_type: str | None = Query(default=None),
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
    if link_type in ("product", "internal", "external"):
        base = base.where(LinkCheckViolation.link_type == link_type)
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
        classify_config=run.classify_config,
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
    view: Literal["active", "all", "dismissed", "solved"] = Query(default="active"),
    link_type: Literal["all", "product", "internal", "external"] = Query(
        default="all"
    ),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TranslationTableResponse:
    """The translation raw-table view: per row, the link breakdown (original /
    expected / translation-tagged / mismatches), computed on demand from the
    source columns + the run's translation_config. Nothing is materialized into
    the bulk table.

    ``view``: ``active`` (default) = rows with a live, unsolved wrong/made-up
    link (corrected links are hidden — they live in the ``solved`` view);
    ``solved`` = rows whose wrong links a fix/replace run already corrected,
    shown struck through; ``dismissed`` = rows with dismissed errors, mismatches
    = the dismissed ones (for restoring); ``all`` = every row with links,
    mismatches = all errors (dismissed flagged). 400 if the run isn't a
    translation run."""
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
    default_langs = cfg.get("product_default_langs", {}) or {}
    internal_t = cfg.get("internal_treatment", "skip")
    external_t = cfg.get("external_treatment", "skip")

    # Dismissed (row_id, link) pairs for this run.
    dismissed: set[tuple[int, str]] = {
        (r, l)
        for (r, l) in (
            await db.execute(
                select(LinkCheckDismissal.row_id, LinkCheckDismissal.link).where(
                    LinkCheckDismissal.run_id == run_id
                )
            )
        ).all()
    }

    # Links a fix/replace run has since corrected (stamped on the stored
    # violations by the in-place re-verify). Keyed per row by normalized link so
    # the overview can strike them through — both ones still present (corrected
    # into a separate column) and ones now gone (replaced in place), the latter
    # re-injected as struck "ghost" entries. Only the output-side (hallucinated)
    # violations correspond to the wrong links shown in the translation column.
    from app.services.link_check import normalize_link as _norm_link

    solved_by_row: dict[int, dict[str, str]] = defaultdict(dict)
    for (r, link) in (
        await db.execute(
            select(LinkCheckViolation.row_id, LinkCheckViolation.link).where(
                LinkCheckViolation.run_id == run_id,
                LinkCheckViolation.problem == "hallucinated",
                LinkCheckViolation.resolution == "solved",
            )
        )
    ).all():
        if link:
            solved_by_row[r][_norm_link(link)] = link

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
        lang_val = (vals.get(lang_col) or "").strip()
        bd = compute_row_breakdown(
            vals.get(orig_col),
            vals.get(trans_col),
            lang_val,
            internal_domains=internal_domains,
            product_domains=product_domains,
            exceptions=exceptions,
            internal_treatment=internal_t,
            external_treatment=external_t,
            default_langs=default_langs,
        )

        solved = solved_by_row.get(rid, {})
        translation = [
            TranslationLinkTag(
                url=t["url"],
                kind=t["kind"],
                dismissed=(rid, t["url"]) in dismissed,
                resolved=t["kind"] != "ok" and _norm_link(t["url"]) in solved,
                expected=t.get("expected"),
                original=t.get("original"),
                link_type=t.get("link_type"),
            )
            for t in bd["translation"]
        ]
        # The link-type filter must ALSO hide the other types' links inside each
        # kept row — the frontend renders this `translation` list directly, so
        # without this a Product-filtered row still showed its internal/external
        # links beside the product ones. (The `aligned` list below was already
        # type-filtered; `translation` is what the table actually renders.)
        if link_type != "all":
            translation = [tl for tl in translation if tl.link_type == link_type]

        # Corrected links that are no longer present in the cell (an in-place
        # replace removed them) → re-inject as struck "ghost" entries so the
        # "solved" view still lists everything a fix/replace run handled. Ghosts
        # carry no link_type, so they're only meaningful at the default "all".
        ghosts: list[TranslationLinkTag] = []
        if link_type == "all":
            live_norms = {_norm_link(tl.url) for tl in translation if tl.kind != "ok"}
            for norm, raw in solved.items():
                if norm not in live_norms:
                    ghosts.append(
                        TranslationLinkTag(
                            url=raw, kind="discrepancy", dismissed=False, resolved=True
                        )
                    )
        resolved_n = sum(1 for tl in translation if tl.resolved) + len(ghosts)

        # Corrected links now have their own "solved" view; the active overview
        # shows only links still needing attention.
        if view == "active":
            translation = [tl for tl in translation if not tl.resolved]
        elif view == "solved":
            translation = [tl for tl in translation if tl.resolved] + ghosts

        # Build the aligned rows, applying the view filter to the WRONG side.
        # active: keep only lines whose wrong is a live error; dismissed: only
        # dismissed wrongs; all: every line (dismissed wrongs flagged).
        aligned: list[AlignedRow] = []
        active_n = 0
        dismissed_n = 0
        for a in bd["aligned"]:
            if link_type != "all" and a["link_type"] != link_type:
                continue
            w = a["wrong"]
            d = bool(w) and (rid, w["url"]) in dismissed
            w_solved = bool(w) and _norm_link(w["url"]) in solved
            if w:
                if d:
                    dismissed_n += 1
                elif not w_solved:
                    active_n += 1
            if view == "active":
                # Live, unsolved, non-dismissed wrongs only.
                if not (w and not d and not w_solved):
                    continue
                wrong_tag = TranslationLinkTag(url=w["url"], kind=w["kind"], dismissed=False)
            elif view == "solved":
                if not (w and w_solved):
                    continue
                wrong_tag = TranslationLinkTag(
                    url=w["url"], kind=w["kind"], dismissed=False, resolved=True
                )
            elif view == "dismissed":
                if not (w and d):
                    continue
                wrong_tag = TranslationLinkTag(url=w["url"], kind=w["kind"], dismissed=True)
            else:  # all
                wrong_tag = (
                    TranslationLinkTag(url=w["url"], kind=w["kind"], dismissed=d)
                    if w
                    else None
                )
                if a["expected"] is None and wrong_tag is None:
                    continue
            aligned.append(AlignedRow(expected=a["expected"], wrong=wrong_tag))

        if view == "active":
            # Only rows that still have a live, unsolved error.
            if active_n == 0:
                continue
        elif view == "solved":
            if resolved_n == 0:
                continue
        elif view == "dismissed":
            if dismissed_n == 0:
                continue
        elif not (bd["original"] or translation or aligned):
            continue

        filtered.append(
            TranslationTableRow(
                row_id=rid,
                row_position=pos,
                lang=lang_val,
                original=bd["original"],
                translation=translation,
                aligned=aligned,
                has_discrepancy=active_n > 0,
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


@router.post(
    "/link-check-runs/{run_id}/translation-table/dismiss", status_code=204
)
async def dismiss_translation_errors(
    run_id: int,
    payload: DismissRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Bulk-dismiss reviewed translation errors (per row+link). Idempotent."""
    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if not run.translation_config:
        raise HTTPException(status_code=400, detail="Not a translation run.")
    rows = [
        {
            "run_id": run_id,
            "row_id": it.row_id,
            "link": it.link,
            "created_by_id": actor.id,
        }
        for it in payload.items
        if it.link.strip()
    ]
    if rows:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        await db.execute(
            pg_insert(LinkCheckDismissal)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_lc_dismissal_run_row_link")
        )
        await db.commit()
    return Response(status_code=204)


@router.post(
    "/link-check-runs/{run_id}/translation-table/restore", status_code=204
)
async def restore_translation_errors(
    run_id: int,
    payload: DismissRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Un-dismiss previously dismissed errors (per row+link)."""
    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    for it in payload.items:
        await db.execute(
            delete(LinkCheckDismissal).where(
                LinkCheckDismissal.run_id == run_id,
                LinkCheckDismissal.row_id == it.row_id,
                LinkCheckDismissal.link == it.link,
            )
        )
    await db.commit()
    return Response(status_code=204)


@router.post(
    "/link-check-runs/{run_id}/translation-table/replace",
    response_model=LinkFixRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replace_translation_links(
    run_id: int,
    payload: DismissRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRun:
    """Deterministically swap each selected WRONG translation link for its
    expected link, IN-PLACE in the translated-content cell — recorded as a
    revertable ``link_fix_runs`` job (``method='replace'``) so it sits beside
    the AI corrections in the same history, with before/after snapshots and a
    Revert button.

    The expected link is recomputed server-side (never trusted from the
    client), so only a genuine discrepancy that pairs to an expected link is
    swapped; an invented / "no good match" link has its ``<a>`` wrapper dropped
    (anchor text kept). Runs as a distributed, revertable background job (one
    pending cell per row fanned out to the ``linkfix.replace_cell`` worker) so
    the run page shows live progress. Cell status is preserved and any cached
    translation cleared, mirroring the AI-fix path."""
    from app.tasks.link_fix import replace_cell as replace_cell_task

    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    cfg = run.translation_config
    if not cfg:
        raise HTTPException(status_code=400, detail="Not a translation run.")
    trans_col = int(cfg["translated_column_id"])

    # Selected wrong links grouped by row.
    want: dict[int, set[str]] = defaultdict(set)
    for it in payload.items:
        if it.link.strip():
            want[it.row_id].add(it.link)
    if not want:
        raise HTTPException(status_code=400, detail="No links selected to replace.")

    row_ids = list(want.keys())
    trans_col_name = (
        await db.execute(
            select(BulkTableColumn.name).where(BulkTableColumn.id == trans_col)
        )
    ).scalar_one_or_none() or "—"
    row_positions = dict(
        (
            await db.execute(
                select(BulkTableRow.id, BulkTableRow.position).where(
                    BulkTableRow.id.in_(row_ids)
                )
            )
        ).all()
    )
    # Snapshot each row's current translated-cell value as its source_value.
    trans_vals = dict(
        (
            await db.execute(
                select(BulkTableCell.row_id, BulkTableCell.value).where(
                    BulkTableCell.row_id.in_(row_ids),
                    BulkTableCell.column_id == trans_col,
                )
            )
        ).all()
    )

    # One pending cell per row, carrying the links to swap; the deterministic
    # replace worker re-derives the expected link and rewrites in place.
    fix_run = LinkFixRun(
        table_id=run.table_id,
        source_run_id=run.id,
        created_by_id=actor.id,
        status="running",
        method="replace",
        target_column_id=None,  # overwrite the translated column in place
        column_ids=[trans_col],
        expected_column_ids=[],
        total=len(row_ids),
        started_at=datetime.now(timezone.utc),
        last_progress_at=datetime.now(timezone.utc),
    )
    db.add(fix_run)
    await db.flush()  # fix_run.id

    fix_cells = [
        LinkFixCell(
            run_id=fix_run.id,
            row_id=rid,
            row_position=row_positions.get(rid, 0),
            column_id=trans_col,
            column_name=trans_col_name,
            state="pending",
            source_value=trans_vals.get(rid),
            violations=[
                {
                    "problem": "hallucinated",
                    "link": link,
                    "detail_code": "not_in_expected",
                    "status_code": None,
                }
                for link in sorted(want[rid])
            ],
        )
        for rid in row_ids
    ]
    db.add_all(fix_cells)
    await db.commit()

    for c in fix_cells:
        replace_cell_task.delay(fix_run.id, c.id)

    await db.refresh(fix_run)
    return fix_run


@router.post(
    "/link-check-runs/{run_id}/strip-links",
    response_model=LinkFixRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def strip_crawl_links(
    run_id: int,
    payload: StripLinksRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRun:
    """Deterministically remove each selected crawl (HTTP-status) link from the
    cell it was flagged in — drop the ``<a>`` wrapper (or markdown link) and
    keep the anchor text — recorded as a revertable ``link_fix_runs`` job
    (``method='strip'``) so it sits beside the AI / replace corrections in the
    same history, with before/after snapshots and a Revert button.

    Unlike the translation replace there's no expected link to swap to (a broken
    link has none), so the action is a pure unwrap. Runs as a distributed,
    revertable background job (one pending cell per row+column fanned out to the
    ``linkfix.strip_cell`` worker); each done cell stamps the source run's
    matching crawl violations ``solved`` so the run page strikes them through."""
    from app.tasks.link_fix import strip_cell as strip_cell_task

    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if not run.check_crawl:
        raise HTTPException(
            status_code=400,
            detail="Stripping links is only available for crawl (HTTP-status) runs.",
        )

    # Selected links grouped by (row, column); only the run's scanned columns
    # are touchable (the items come from this run's violations, but never trust
    # the client to name an arbitrary cell).
    scanned = {int(c) for c in (run.column_ids or [])}
    by_cell: dict[tuple[int, int], set[str]] = defaultdict(set)
    for it in payload.items:
        if it.link.strip() and (not scanned or it.column_id in scanned):
            by_cell[(it.row_id, it.column_id)].add(it.link)
    if not by_cell:
        raise HTTPException(status_code=400, detail="No links selected to strip.")

    col_ids = sorted({c for _r, c in by_cell})
    row_ids = sorted({r for r, _c in by_cell})
    col_names = dict(
        (
            await db.execute(
                select(BulkTableColumn.id, BulkTableColumn.name).where(
                    BulkTableColumn.id.in_(col_ids)
                )
            )
        ).all()
    )
    row_positions = dict(
        (
            await db.execute(
                select(BulkTableRow.id, BulkTableRow.position).where(
                    BulkTableRow.id.in_(row_ids)
                )
            )
        ).all()
    )
    # Snapshot each touched cell's current value as its source_value.
    cell_vals = {
        (r, c): v
        for r, c, v in (
            await db.execute(
                select(
                    BulkTableCell.row_id,
                    BulkTableCell.column_id,
                    BulkTableCell.value,
                ).where(
                    BulkTableCell.row_id.in_(row_ids),
                    BulkTableCell.column_id.in_(col_ids),
                )
            )
        ).all()
    }

    fix_run = LinkFixRun(
        table_id=run.table_id,
        source_run_id=run.id,
        created_by_id=actor.id,
        status="running",
        method="strip",
        target_column_id=None,  # overwrite the scanned column in place
        column_ids=col_ids,
        expected_column_ids=[],
        total=len(by_cell),
        started_at=datetime.now(timezone.utc),
        last_progress_at=datetime.now(timezone.utc),
    )
    db.add(fix_run)
    await db.flush()  # fix_run.id

    fix_cells = [
        LinkFixCell(
            run_id=fix_run.id,
            row_id=rid,
            row_position=row_positions.get(rid, 0),
            column_id=cid,
            column_name=col_names.get(cid, "—"),
            state="pending",
            source_value=cell_vals.get((rid, cid)),
            violations=[
                {
                    "problem": "broken",
                    "link": link,
                    "detail_code": None,
                    "status_code": None,
                }
                for link in sorted(links)
            ],
        )
        for (rid, cid), links in by_cell.items()
    ]
    db.add_all(fix_cells)
    await db.commit()

    for c in fix_cells:
        strip_cell_task.delay(fix_run.id, c.id)

    await db.refresh(fix_run)
    return fix_run


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


@router.post(
    "/link-check-runs/{run_id}/retry-failed", response_model=LinkCheckRunRead
)
async def retry_failed_link_check(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkCheckRun:
    """Re-crawl ONLY the failed links of a finished crawl run, in place.

    Resets every target that came back not-OK (4xx / 5xx / network error) to
    ``pending``, drops the ``broken`` violations it produced, re-baselines the
    counters, flips the run back to ``running`` and re-enqueues the crawl. So a
    transient failure (timeout, momentary 5xx, DNS blip) can be re-checked
    without re-crawling the healthy links or starting a fresh run. Healthy
    (``ok``) links and any juxtapose violations are untouched. 400 if the run
    never crawled or has no failed links; 409 while it's still active."""
    run = await _get_link_check_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")
    if not run.check_crawl:
        raise HTTPException(
            status_code=400,
            detail="Retry failed is only available for crawl (HTTP-status) runs.",
        )
    if run.status not in ("done", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Run is {run.status}; wait for it to finish before retrying.",
        )

    failed = (
        await db.execute(
            select(func.count())
            .select_from(LinkCheckCrawlTarget)
            .where(
                LinkCheckCrawlTarget.run_id == run_id,
                LinkCheckCrawlTarget.ok.is_(False),
            )
        )
    ).scalar_one()
    if failed == 0:
        raise HTTPException(status_code=400, detail="No failed links to retry.")

    # Reset the failed targets and drop the broken violations they produced —
    # the re-crawl writes fresh ones. A 'broken' violation always maps to an
    # ok=False target, so that's the exact set to clear; 'ok' violations
    # (healthy links, include_ok mode) are left alone.
    await db.execute(
        update(LinkCheckCrawlTarget)
        .where(
            LinkCheckCrawlTarget.run_id == run_id,
            LinkCheckCrawlTarget.ok.is_(False),
        )
        .values(state="pending", ok=None, status_code=None, detail_code=None)
    )
    await db.execute(
        delete(LinkCheckViolation).where(
            LinkCheckViolation.run_id == run_id,
            LinkCheckViolation.problem == "broken",
        )
    )

    # Re-baseline the crawl counters from the still-done targets; the re-crawl
    # bumps them back up and finalize recomputes authoritative totals.
    done_ct = (
        await db.execute(
            select(func.count())
            .select_from(LinkCheckCrawlTarget)
            .where(
                LinkCheckCrawlTarget.run_id == run_id,
                LinkCheckCrawlTarget.state == "done",
            )
        )
    ).scalar_one()
    ok_ct = (
        await db.execute(
            select(func.count())
            .select_from(LinkCheckCrawlTarget)
            .where(
                LinkCheckCrawlTarget.run_id == run_id,
                LinkCheckCrawlTarget.state == "done",
                LinkCheckCrawlTarget.ok.is_(True),
            )
        )
    ).scalar_one()
    run.crawled = int(done_ct)
    run.ok_count = int(ok_ct)
    run.broken_count = int(done_ct) - int(ok_ct)
    run.status = "running"
    run.error = None
    run.finished_at = None
    run.last_progress_at = datetime.now(timezone.utc)
    await db.commit()

    # Fan the reset (pending) chunks back out via the resume task.
    resume_link_check.delay(run_id)
    await db.refresh(run)
    return run


# ---------- AI link fix (content tool) ----------

_FIXABLE_PROBLEMS = ("omitted", "broken", "hallucinated")


async def _get_link_fix_run_or_404(db: AsyncSession, run_id: int) -> LinkFixRun:
    run = await db.get(LinkFixRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Link-fix run not found")
    return run


def _pick_named_column(
    existing: list[tuple[int, str]], requested: str
) -> int | None:
    """Id of the first existing column whose name matches ``requested``, or
    None. Match is case- and surrounding-space-insensitive so re-running a fix
    with the same target name reuses the column instead of duplicating it.
    Pure (no DB) so the reuse rule is unit-testable on its own.
    """
    key = requested.strip().lower()
    for col_id, name in existing:
        if (name or "").strip().lower() == key:
            return col_id
    return None


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

    # Scope to the translation overview's link-type filter (product/internal/
    # external) when the caller passes one. Translation runs don't persist
    # link_type on the violation rows (it's computed live in the table view),
    # so classify each link's host here against the run's domains; crawl runs
    # store it, so use the stored value.
    if payload.link_type in ("product", "internal", "external"):
        if source.translation_config:
            from app.services.translation_links import (
                classify_link,
                normalize_domain,
                parse_domains,
            )

            cfg = source.translation_config
            prod = [normalize_domain(d) for d in (cfg.get("product_domains") or [])]
            dom_cols = [int(c) for c in cfg.get("internal_domain_column_ids", [])]
            v_rows = {v.row_id for v in violations}
            internal_by_row: dict[int, list[str]] = defaultdict(list)
            if dom_cols and v_rows:
                for c in (
                    (
                        await db.execute(
                            select(BulkTableCell).where(
                                BulkTableCell.row_id.in_(v_rows),
                                BulkTableCell.column_id.in_(dom_cols),
                            )
                        )
                    )
                    .scalars()
                    .all()
                ):
                    internal_by_row[c.row_id] += parse_domains(c.value)
            violations = [
                v
                for v in violations
                if classify_link(
                    v.link, internal_by_row.get(v.row_id, []), prod
                )
                == payload.link_type
            ]
        else:
            violations = [v for v in violations if v.link_type == payload.link_type]

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

    # Resolve where corrected content goes. new_column_name lands in a column
    # of that name — reusing one that already exists, else creating it; an
    # explicit target_column_id reuses a chosen column; neither = overwrite the
    # scanned source column (target_column_id stays NULL).
    target_column_id: int | None = None
    if payload.new_column_name and payload.new_column_name.strip():
        requested = payload.new_column_name.strip()[:120]
        # Don't pile up duplicate columns: re-running the fix with the same
        # name (the default "Fixed links", most often) should feed the column
        # that's already there, not spawn a second one beside it. Match an
        # existing column by name, case- and surrounding-space-insensitive; a
        # user who genuinely wants a separate column types a different name.
        cols = (
            await db.execute(
                select(BulkTableColumn.id, BulkTableColumn.name, BulkTableColumn.position)
                .where(BulkTableColumn.table_id == table_id)
                .order_by(BulkTableColumn.position)
            )
        ).all()
        existing_id = _pick_named_column([(c.id, c.name) for c in cols], requested)
        if existing_id is not None:
            # Same as picking it as the target: overwrite only the corrected
            # cells, leave the rest of the column untouched.
            target_column_id = existing_id
        else:
            next_pos = max((c.position for c in cols), default=-1) + 1
            new_col = BulkTableColumn(
                table_id=table_id,
                position=int(next_pos),
                name=requested,
                kind="output",
            )
            db.add(new_col)
            await db.flush()
            target_column_id = new_col.id

            # Publish-readiness: a freshly-created column must hold EVERY row,
            # not just the flagged ones, so it can be published as a complete
            # column. Copy all cells of the single scanned source column into
            # it up front; the fix workers then overwrite the corrected rows.
            # (Link checks scan a single output column, so there's one
            # unambiguous source.) Not needed when reusing an existing column —
            # it already has its own content.
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

    # For replace / strip runs, report how many individual links were actually
    # changed (the unit the user selected), not just how many cells — each done
    # cell's `violations` holds the links it applied.
    links_changed: int | None = None
    if run.method in ("replace", "strip"):
        applied = (
            await db.execute(
                select(LinkFixCell.violations).where(
                    LinkFixCell.run_id == run_id,
                    LinkFixCell.state == "done",
                )
            )
        ).scalars().all()
        links_changed = sum(len(v or []) for v in applied)

    return LinkFixRunDetail(
        id=run.id,
        table_id=run.table_id,
        name=run.name,
        source_run_id=run.source_run_id,
        recheck_run_id=run.recheck_run_id,
        target_column_id=run.target_column_id,
        method=run.method,  # type: ignore[arg-type]
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
        last_progress_at=run.last_progress_at,
        created_by_name=await _resolve_creator_name(db, run.created_by_id),
        page=page,
        page_size=page_size,
        total_cells=int(total),
        links_changed=links_changed,
        items=[_fix_cell_read(c) for c in rows],
    )


def _fix_cell_read(c: LinkFixCell) -> LinkFixCellRead:
    """Build the read model with the aligned Before/After diff blocks (only
    meaningful once the cell is done)."""
    item = LinkFixCellRead.model_validate(c)
    if c.state == "done":
        before = c.source_value or c.old_value or ""
        after = c.new_value or ""
        item.diff_blocks = [DiffBlock(**b) for b in aligned_diff(before, after)]
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


@router.post("/link-fix-runs/{run_id}/revert", response_model=LinkFixRevertResult)
async def revert_link_fix_run(
    run_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFixRevertResult:
    """Restore the pre-fix value of every cell this run changed.

    Idempotent. A cell is skipped if its current value no longer matches the
    value the fix wrote (someone edited or regenerated it since) — reverting
    would otherwise discard that later change. The reverted/skipped counts let
    the UI explain a partial or no-op revert instead of looking like nothing
    happened."""
    run = await _get_link_fix_run_or_404(db, run_id)
    await _get_table_or_404(db, run.table_id, actor, level="write")

    def _result(reverted: int, skipped: int) -> LinkFixRevertResult:
        return LinkFixRevertResult(
            **LinkFixRunRead.model_validate(run).model_dump(),
            reverted_count=reverted,
            skipped_count=skipped,
        )

    if run.reverted_at is not None:
        return _result(0, 0)

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
    reverted = 0
    skipped = 0
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
            reverted += 1
        else:
            skipped += 1

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
    return _result(reverted, skipped)


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
) -> StreamingResponse:
    """Stream the table to CSV.

    ACL + the (small) column header are resolved here on the request session;
    the row/cell body is streamed in batches by ``stream_table_csv`` on its own
    session (see there). Streaming keeps peak memory flat regardless of table
    size — the old path built the whole CSV + a gzip copy in RAM and tripped the
    prod api memory cap on large tables.
    """
    t = await _get_table_or_404(db, table_id, actor, level="read")
    col_rows = (
        await db.execute(
            select(BulkTableColumn.id, BulkTableColumn.name)
            .where(BulkTableColumn.table_id == table_id)
            .order_by(BulkTableColumn.position, BulkTableColumn.id)
        )
    ).all()
    columns = [(c.id, c.name) for c in col_rows]
    return StreamingResponse(
        stream_table_csv(table_id, columns),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": content_disposition(f"{t.name}.csv")},
    )


# ----- background CSV export (build in a worker, download the prepared blob) ---
#
# The synchronous export.csv above is fine for small/medium tables, but a single
# long HTTP download of a very large table trips the response timeout of the
# proxy/CDN in front of prod. These three endpoints decouple it: queue a build,
# poll status, then download the pre-built (gzipped) blob in a fast request.


@router.post(
    "/tables/{table_id}/export-jobs",
    response_model=CsvExportJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_export_job(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CsvExportJobRead:
    """Queue a background CSV export (ACL = table read). Poll
    ``GET /library/export-jobs/{id}`` until status == 'done', then download."""
    table = await _get_table_or_404(db, table_id, actor, level="read")
    job = await csv_export_svc.create_job(db, table, actor)
    build_csv_export.delay(job.id)
    return csv_export_svc.to_read(job)


@router.get("/export-jobs/{job_id}", response_model=CsvExportJobRead)
async def get_export_job(
    job_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CsvExportJobRead:
    job = await csv_export_svc.get_job(db, job_id, actor)
    return csv_export_svc.to_read(job)


@router.get("/export-jobs/{job_id}/download")
async def download_export_job(
    job_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Serve the pre-built gzipped CSV. No generation happens here, so it can't
    hit the proxy timeout. We send the stored bytes as-is with
    ``Content-Encoding: gzip``; the browser decompresses to a plain .csv."""
    blob, filename = await csv_export_svc.load_blob_for_download(db, job_id, actor)
    return Response(
        content=blob,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": content_disposition(filename),
            "Content-Encoding": "gzip",
        },
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
    payload: AutotoolEnableRequest | None = None,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutotoolState:
    t = await _get_table_or_404(db, table_id, actor, level="write")
    if not t.autotool_token:
        t.autotool_token = uuid.uuid4().hex  # 32 hex chars, 128 bits
    t.autotool_enabled = True
    # Optional column selection. A body with column_ids=null (or every column
    # selected) stores None = "all"; a strict subset is stored as-is; foreign or
    # empty ids collapse to None. No body at all leaves the existing selection
    # untouched (so a plain re-enable doesn't wipe it).
    if payload is not None:
        if payload.column_ids is None:
            t.autotool_column_ids = None
        else:
            valid_ids = set(
                (
                    await db.execute(
                        select(BulkTableColumn.id).where(
                            BulkTableColumn.table_id == table_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            picked = [cid for cid in payload.column_ids if cid in valid_ids]
            t.autotool_column_ids = (
                picked if picked and set(picked) != valid_ids else None
            )
    # Capture before commit; expire_on_commit would otherwise require a reload.
    token = t.autotool_token
    column_ids = t.autotool_column_ids
    await db.commit()
    return AutotoolState(
        autotool_enabled=True,
        autotool_token=token,
        csv_path=f"/autotool/{token}.csv",
        column_ids=column_ids,
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
