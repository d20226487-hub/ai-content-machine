"""Folder CRUD for the /publish/domains Drive-style tree.

Mirrors ``api/categories.py`` (prompts tree). Access is admin or
manager, matching the /domains router.

Endpoints:
  GET    /domain-folders                — flat list (or with_counts)
  POST   /domain-folders                — create
  PATCH  /domain-folders/{id}           — rename / move (cycle-checked)
  DELETE /domain-folders/{id}           — refuses non-empty folders
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.models import Domain, DomainFolder, User
from app.db.session import get_db
from app.schemas.domain_folder import (
    DomainFolderCreate,
    DomainFolderRead,
    DomainFolderUpdate,
)

router = APIRouter(
    prefix="/domain-folders",
    tags=["domain-folders"],
    dependencies=[Depends(require_role("admin", "manager"))],
)


async def _get_or_404(db: AsyncSession, folder_id: int) -> DomainFolder:
    folder = (
        await db.execute(
            select(DomainFolder).where(DomainFolder.id == folder_id)
        )
    ).scalar_one_or_none()
    if folder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
        )
    return folder


async def _would_create_cycle(
    db: AsyncSession, folder_id: int, new_parent_id: int | None
) -> bool:
    """Walk up from new_parent_id; if we hit folder_id, it's a cycle.

    Also short-circuits on a self-loop via ``seen`` — if the DB somehow
    already contained a cycle (shouldn't, RESTRICT FK prevents it), we
    detect that too instead of looping forever.
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
                select(DomainFolder.parent_id).where(DomainFolder.id == cursor)
            )
        ).scalar_one_or_none()
    return False


@router.get("", response_model=list[DomainFolderRead])
async def list_folders(
    with_counts: bool = Query(
        default=False,
        description=(
            "When true, augment each row with `domain_count` (direct, "
            "non-trashed children) and `subfolder_count`. Skipped by "
            "default to keep the payload tiny for picker-style consumers."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> list[DomainFolderRead]:
    """Flat list of folders, ordered by name. The Drive-style UI
    re-assembles this into a tree client-side using parent_id."""
    rows = list(
        (
            await db.execute(
                select(DomainFolder).order_by(DomainFolder.name)
            )
        )
        .scalars()
        .all()
    )
    if not with_counts:
        return [DomainFolderRead.model_validate(f) for f in rows]

    # Direct (non-trashed) domain count per folder.
    domain_counts = dict(
        (
            await db.execute(
                select(Domain.folder_id, func.count(Domain.id))
                .where(
                    Domain.folder_id.is_not(None),
                    Domain.deleted_at.is_(None),
                )
                .group_by(Domain.folder_id)
            )
        ).all()
    )
    # Direct subfolder count per folder (folders whose parent_id == id).
    subfolder_counts = dict(
        (
            await db.execute(
                select(DomainFolder.parent_id, func.count(DomainFolder.id))
                .where(DomainFolder.parent_id.is_not(None))
                .group_by(DomainFolder.parent_id)
            )
        ).all()
    )
    out: list[DomainFolderRead] = []
    for f in rows:
        rec = DomainFolderRead.model_validate(f)
        rec.domain_count = int(domain_counts.get(f.id, 0))
        rec.subfolder_count = int(subfolder_counts.get(f.id, 0))
        out.append(rec)
    return out


@router.post(
    "", response_model=DomainFolderRead, status_code=status.HTTP_201_CREATED,
)
async def create_folder(
    payload: DomainFolderCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DomainFolder:
    if payload.parent_id is not None:
        await _get_or_404(db, payload.parent_id)
    folder = DomainFolder(
        name=payload.name.strip(),
        parent_id=payload.parent_id,
        created_by_id=actor.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.patch("/{folder_id}", response_model=DomainFolderRead)
async def update_folder(
    folder_id: int,
    payload: DomainFolderUpdate,
    db: AsyncSession = Depends(get_db),
) -> DomainFolder:
    folder = await _get_or_404(db, folder_id)
    data = payload.model_dump(exclude_unset=True)

    if "parent_id" in data:
        new_parent = data["parent_id"]
        if new_parent is not None:
            await _get_or_404(db, new_parent)
        if await _would_create_cycle(db, folder_id, new_parent):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Move would create a cycle in the folder tree.",
            )
        folder.parent_id = new_parent

    if "name" in data and data["name"] is not None:
        folder.name = data["name"].strip()

    await db.commit()
    await db.refresh(folder)
    return folder


@router.delete(
    "/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # response_class=Response avoids FastAPI's "204 must not have a body"
    # assert that fires when the function's `-> None` return type is
    # inferred as a non-empty response_model. Same pattern as the
    # /domains/{id}/permanent endpoint above.
    response_class=Response,
)
async def delete_folder(
    folder_id: int, db: AsyncSession = Depends(get_db)
) -> Response:
    """Delete a folder. Refuses if it's non-empty (any domain still
    references it, or it has subfolders). The user must move the
    contents elsewhere first — same UX as Prompts categories.

    Application-level check first so the user gets a friendly 400 with
    the actual reason. The DB-level RESTRICT FK is belt-and-braces
    against direct SQL deletes that would bypass us.
    """
    folder = await _get_or_404(db, folder_id)

    direct_subfolders = int(
        (
            await db.execute(
                select(func.count(DomainFolder.id)).where(
                    DomainFolder.parent_id == folder_id
                )
            )
        ).scalar_one()
    )
    direct_domains = int(
        (
            await db.execute(
                select(func.count(Domain.id)).where(
                    Domain.folder_id == folder_id,
                    Domain.deleted_at.is_(None),
                )
            )
        ).scalar_one()
    )
    if direct_subfolders + direct_domains > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Folder is not empty: {direct_domains} domain(s) and "
                f"{direct_subfolders} subfolder(s). Move them elsewhere "
                f"before deleting."
            ),
        )
    try:
        await db.delete(folder)
        await db.commit()
    except IntegrityError:
        # Should not happen — the count check above caught it — but
        # belt-and-braces in case a concurrent insert raced us.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder is not empty (raced with another change).",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
