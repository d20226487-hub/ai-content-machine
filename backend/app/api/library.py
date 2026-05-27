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
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select, update
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
    User,
)
from app.db.session import get_db
from app.schemas.bulk import (
    BulkGenerationRunDetail,
    BulkGenerationRunRead,
    CellsBatchUpsert,
    CellUpsert,
    ColumnCreate,
    ColumnRead,
    ColumnUpdate,
    CsvImportRequest,
    FolderCreate,
    FolderRead,
    FolderUpdate,
    GenerateRequest,
    GenerateResponse,
    RowRead,
    TableBulkMove,
    TableCreate,
    TableListItem,
    TableListResponse,
    TableRead,
    TableUpdate,
    TrashBulkIds,
)
from app.tasks.bulk_generation import generate_bulk_cell

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
                }
                for c in cells
            ],
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
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRead:
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
    col_q = select(BulkTableColumn).where(
        BulkTableColumn.table_id == table_id,
        BulkTableColumn.kind == "output",
        BulkTableColumn.prompt_id.is_not(None),
    )
    if payload.column_ids:
        col_q = col_q.where(BulkTableColumn.id.in_(payload.column_ids))
    cols = (await db.execute(col_q)).scalars().all()

    if not cols:
        return GenerateResponse(
            enqueued_cell_ids=[], skipped=0,
            message=(
                "Nothing to do: no output columns with prompts. "
                "Configure a prompt on an output column first."
            ),
        )

    # Resolve target rows.
    row_q = select(BulkTableRow).where(BulkTableRow.table_id == table_id).order_by(
        BulkTableRow.position
    )
    if payload.row_ids:
        row_q = row_q.where(BulkTableRow.id.in_(payload.row_ids))
    rows = (await db.execute(row_q)).scalars().all()

    if not rows:
        return GenerateResponse(
            enqueued_cell_ids=[], skipped=0, message="No rows to generate."
        )

    # Existing cells lookup, to detect what to skip.
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

    # Resolve effective mode: legacy `overwrite=True` maps to mode='all'.
    effective_mode = "all" if payload.overwrite else payload.mode

    # Compute the include set first; THEN do one bulk DB write; THEN enqueue.
    # The previous version was per-cell `_ensure_cell + UPDATE + COMMIT`, which
    # is roughly 3 round trips × N cells. For a 10k×5 table with all cells
    # included that was 150k round trips inside one HTTP request — minutes of
    # latency just for the bookkeeping. Bulk INSERT … ON CONFLICT … RETURNING
    # collapses it to a single statement.
    to_enqueue: list[tuple[int, int]] = []  # (row_id, column_id)
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


@router.get("/tables/{table_id}/export.csv")
async def export_csv(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t = await _get_table_or_404(db, table_id, actor, level="read", full=True)
    cells = []
    if t.rows:
        cells = (
            (
                await db.execute(
                    select(BulkTableCell).where(
                        BulkTableCell.row_id.in_([r.id for r in t.rows])
                    )
                )
            )
            .scalars()
            .all()
        )
    cell_lookup = {(c.row_id, c.column_id): c.value or "" for c in cells}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c.name for c in t.columns])
    for r in t.rows:
        writer.writerow([cell_lookup.get((r.id, c.id), "") for c in t.columns])

    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in t.name)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'},
    )
