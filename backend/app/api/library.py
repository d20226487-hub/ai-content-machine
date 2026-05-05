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

from app.api.deps import get_current_user
from app.db.models import (
    BulkTable,
    BulkTableCell,
    BulkTableColumn,
    BulkTableFolder,
    BulkTableRow,
    User,
)
from app.db.session import get_db
from app.schemas.bulk import (
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
    TableCreate,
    TableListItem,
    TableListResponse,
    TableRead,
    TableUpdate,
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
) -> BulkTable:
    stmt = select(BulkTable).where(BulkTable.id == table_id)
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
                .where(BulkTable.folder_id.is_not(None))
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
    in_use = (
        await db.execute(
            select(func.count(BulkTable.id)).where(BulkTable.folder_id == folder_id)
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

    base = select(BulkTable).order_by(BulkTable.updated_at.desc())
    count_stmt = select(func.count(BulkTable.id))
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


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    table_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    t = await _get_table_or_404(db, table_id, actor, level="delete")
    await db.delete(t)
    await db.commit()


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
    if to_enqueue:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        rows_payload = [
            {"row_id": rid, "column_id": cid, "status": "generating", "error": None}
            for rid, cid in to_enqueue
        ]
        stmt = pg_insert(BulkTableCell).values(rows_payload)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_bulk_cells_row_column",
            set_={"status": "generating", "error": None},
        ).returning(BulkTableCell.id)
        result = await db.execute(stmt)
        enqueued = [int(r[0]) for r in result.all()]
        await db.commit()

        # Enqueue Celery tasks AFTER commit so workers don't pick up cells
        # that aren't visible yet. .delay() is just a Redis push, so even a
        # tight loop of N enqueues is in the order of milliseconds for N=10k.
        for rid, cid in to_enqueue:
            generate_bulk_cell.delay(table_id, rid, cid)

    mode_label = {"empty": "empty", "failed": "failed", "all": "all"}[effective_mode]
    msg = f"Enqueued {len(enqueued)} cell(s) (mode: {mode_label})."
    if skipped:
        msg += f" Skipped {skipped} cell(s) that didn't match the filter."
    return GenerateResponse(
        enqueued_cell_ids=enqueued, skipped=skipped, message=msg
    )


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
