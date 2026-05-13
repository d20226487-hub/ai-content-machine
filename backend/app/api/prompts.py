from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_role
from app.db.models import AppSetting, Category, Prompt, PromptVersion, Tag, User
from app.db.session import get_db
from app.providers.base import ProviderError
from app.providers.registry import ProviderNotConfigured
from app.schemas.prompt import (
    PromptCreate,
    PromptDetail,
    PromptDraftRequest,
    PromptDraftResponse,
    PromptListItem,
    PromptListResponse,
    PromptMetaUpdate,
    PromptRevert,
    PromptVersionCreate,
    PromptVersionNoteUpdate,
    PromptVersionRead,
    PromptVersionSummary,
    TrashBulkIds,
)
from app.services.ai_assist import draft_prompt
from app.services.prompts import extract_variables

router = APIRouter(
    prefix="/prompts", tags=["prompts"], dependencies=[Depends(get_current_user)]
)


# ---------- helpers ----------

async def _get_prompt_or_404(
    db: AsyncSession,
    prompt_id: int,
    *,
    include_trashed: bool = False,
) -> Prompt:
    """Fetch a prompt by id.

    By default `deleted_at IS NULL` is required — trashed prompts are
    invisible to every endpoint except the trash surface. Pass
    ``include_trashed=True`` for the preview / restore / permanent-delete
    paths.
    """
    stmt = (
        select(Prompt)
        .options(
            selectinload(Prompt.versions),
            selectinload(Prompt.tags),
        )
        .where(Prompt.id == prompt_id)
        # populate_existing forces re-population of attributes on the in-memory
        # instance, so the joined `current_version` relationship reflects the
        # latest state after a write within the same session.
        .execution_options(populate_existing=True)
    )
    if not include_trashed:
        stmt = stmt.where(Prompt.deleted_at.is_(None))
    p = (await db.execute(stmt)).unique().scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    return p


async def _get_trashed_prompt_or_404(db: AsyncSession, prompt_id: int) -> Prompt:
    """Fetch a prompt that's in the trash. Active surfaces never see it."""
    stmt = (
        select(Prompt)
        .options(selectinload(Prompt.versions), selectinload(Prompt.tags))
        .where(Prompt.id == prompt_id, Prompt.deleted_at.is_not(None))
        .execution_options(populate_existing=True)
    )
    p = (await db.execute(stmt)).unique().scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return p


async def _verify_category(db: AsyncSession, category_id: int) -> None:
    cat = (
        await db.execute(select(Category.id).where(Category.id == category_id))
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown category_id")


async def _resolve_tags(db: AsyncSession, tag_ids: list[int]) -> list[Tag]:
    if not tag_ids:
        return []
    rows = (await db.execute(select(Tag).where(Tag.id.in_(tag_ids)))).scalars().all()
    found = {t.id for t in rows}
    missing = [tid for tid in tag_ids if tid not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tag_id(s): {missing}",
        )
    return list(rows)


async def _user_lookup(
    db: AsyncSession, user_ids: list[int | None]
) -> dict[int, User]:
    """Load distinct non-null user IDs in one query and return {id: User}."""
    ids = {uid for uid in user_ids if uid is not None}
    if not ids:
        return {}
    rows = (
        await db.execute(select(User).where(User.id.in_(ids)))
    ).scalars().all()
    return {u.id: u for u in rows}


def _user_fields(user_id: int | None, lookup: dict[int, User]) -> dict[str, str | None]:
    if user_id is None:
        return {"created_by_name": None, "created_by_email": None}
    u = lookup.get(user_id)
    if u is None:
        return {"created_by_name": None, "created_by_email": None}
    return {"created_by_name": u.full_name, "created_by_email": u.email}


async def _next_version_number(db: AsyncSession, prompt_id: int) -> int:
    current_max = (
        await db.execute(
            select(func.coalesce(func.max(PromptVersion.version_number), 0)).where(
                PromptVersion.prompt_id == prompt_id
            )
        )
    ).scalar_one()
    return int(current_max) + 1


async def _category_descendants(db: AsyncSession, root_id: int) -> set[int]:
    """Return root_id plus all descendant category ids."""
    out: set[int] = {root_id}
    frontier = [root_id]
    while frontier:
        children = (
            await db.execute(select(Category.id).where(Category.parent_id.in_(frontier)))
        ).scalars().all()
        new = [c for c in children if c not in out]
        out.update(new)
        frontier = new
    return out


async def _to_detail_with_users(db: AsyncSession, p: Prompt) -> PromptDetail:
    """Convenience wrapper: load creator info from DB, then build the detail payload."""
    user_ids = [p.created_by_id, *[v.created_by_id for v in p.versions]]
    users = await _user_lookup(db, user_ids)
    return _to_detail(p, users)


def _to_detail(p: Prompt, users: dict[int, User]) -> PromptDetail:
    versions_sorted = sorted(p.versions, key=lambda v: v.version_number, reverse=True)
    current = p.current_version
    return PromptDetail(
        id=p.id,
        name=p.name,
        category_id=p.category_id,
        current_version=(
            PromptVersionRead(
                id=current.id,
                version_number=current.version_number,
                content=current.content,
                change_note=current.change_note,
                created_by_id=current.created_by_id,
                created_at=current.created_at,
                **_user_fields(current.created_by_id, users),
            )
            if current
            else None
        ),
        versions=[
            PromptVersionSummary(
                id=v.id,
                version_number=v.version_number,
                change_note=v.change_note,
                created_by_id=v.created_by_id,
                created_at=v.created_at,
                **_user_fields(v.created_by_id, users),
            )
            for v in versions_sorted
        ],
        tags=p.tags,
        variables=extract_variables(current.content) if current else [],
        created_by_id=p.created_by_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
        **_user_fields(p.created_by_id, users),
    )


# ---------- AI-assisted draft (declared before /{prompt_id} so it isn't shadowed) ----------

@router.post("/draft", response_model=PromptDraftResponse)
async def draft_with_ai(
    payload: PromptDraftRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> PromptDraftResponse:
    try:
        text, code, model = await draft_prompt(
            db,
            description=payload.description,
            provider_code=payload.provider_code,
            model=payload.model,
            user_id=actor.id,
        )
    except ProviderNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return PromptDraftResponse(
        draft_content=text, provider_used=code, model_used=model
    )


# ---------- list ----------

@router.get("", response_model=PromptListResponse)
async def list_prompts(
    category_id: int | None = Query(default=None),
    # When set, the special value 0 means "top-level" (prompts with no folder).
    include_descendants: bool = Query(default=False),
    tag_ids: list[int] | None = Query(
        default=None,
        description=(
            "Filter by one or more tag IDs. AND semantics — a prompt must carry "
            "every requested tag to match. Repeat the param: ?tag_ids=1&tag_ids=2"
        ),
    ),
    q: str | None = Query(default=None, description="Search by prompt name (case-insensitive)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> PromptListResponse:
    from app.db.models import prompt_tags  # local import to avoid circular at module load

    stmt = (
        select(Prompt)
        .options(selectinload(Prompt.tags))
        .where(Prompt.deleted_at.is_(None))
    )
    count_stmt = select(func.count(Prompt.id.distinct())).where(
        Prompt.deleted_at.is_(None)
    )

    if category_id is not None:
        if category_id == 0:
            # Top-level: prompts with no folder
            stmt = stmt.where(Prompt.category_id.is_(None))
            count_stmt = count_stmt.where(Prompt.category_id.is_(None))
        elif include_descendants:
            ids = await _category_descendants(db, category_id)
            stmt = stmt.where(Prompt.category_id.in_(ids))
            count_stmt = count_stmt.where(Prompt.category_id.in_(ids))
        else:
            stmt = stmt.where(Prompt.category_id == category_id)
            count_stmt = count_stmt.where(Prompt.category_id == category_id)

    if tag_ids:
        # AND semantics: keep only prompts that carry every requested tag.
        # The HAVING count must equal the number of distinct requested tags.
        n = len(set(tag_ids))
        sub = (
            select(prompt_tags.c.prompt_id)
            .where(prompt_tags.c.tag_id.in_(tag_ids))
            .group_by(prompt_tags.c.prompt_id)
            .having(func.count(prompt_tags.c.tag_id.distinct()) == n)
        )
        stmt = stmt.where(Prompt.id.in_(sub))
        count_stmt = count_stmt.where(Prompt.id.in_(sub))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Prompt.name.ilike(like)))
        count_stmt = count_stmt.where(or_(Prompt.name.ilike(like)))

    total = int((await db.execute(count_stmt)).scalar_one())

    stmt = (
        stmt.order_by(Prompt.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).unique().scalars().all()

    users = await _user_lookup(db, [r.created_by_id for r in rows])
    out: list[PromptListItem] = []
    for p in rows:
        cv = p.current_version
        cv_field: PromptVersionRead | None = None
        if cv is not None:
            cv_users = await _user_lookup(db, [cv.created_by_id])
            cv_field = PromptVersionRead(
                id=cv.id,
                version_number=cv.version_number,
                content=cv.content,
                change_note=cv.change_note,
                created_by_id=cv.created_by_id,
                created_at=cv.created_at,
                **_user_fields(cv.created_by_id, cv_users),
            )
        out.append(
            PromptListItem(
                id=p.id,
                name=p.name,
                category_id=p.category_id,
                current_version=cv_field,
                tags=p.tags,
                created_by_id=p.created_by_id,
                created_at=p.created_at,
                updated_at=p.updated_at,
                **_user_fields(p.created_by_id, users),
            )
        )
    return PromptListResponse(items=out, total=total, page=page, page_size=page_size)


# ---------- get one ----------

_PROMPT_TRASH_RETENTION_KEY = "prompt_trash_retention_days"
_PROMPT_TRASH_RETENTION_DEFAULT = 50
_PROMPT_TRASH_RETENTION_MAX = 3650


@router.get("/trash/count", response_model=dict)
async def trash_count(db: AsyncSession = Depends(get_db)) -> dict:
    n = int(
        (
            await db.execute(
                select(func.count(Prompt.id)).where(Prompt.deleted_at.is_not(None))
            )
        ).scalar_one()
    )
    return {"count": n}


@router.get("/trash/retention", response_model=dict)
async def get_trash_retention(
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role("admin", "manager")),
) -> dict:
    row = (
        await db.execute(
            select(AppSetting.value).where(
                AppSetting.key == _PROMPT_TRASH_RETENTION_KEY
            )
        )
    ).scalar_one_or_none()
    try:
        days = (
            max(0, int(row))
            if row is not None
            else _PROMPT_TRASH_RETENTION_DEFAULT
        )
    except (TypeError, ValueError):
        days = _PROMPT_TRASH_RETENTION_DEFAULT
    return {
        "days": days,
        "default": _PROMPT_TRASH_RETENTION_DEFAULT,
        "max": _PROMPT_TRASH_RETENTION_MAX,
    }


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
            status_code=400, detail="`days` must be an integer."
        )
    if days < 0 or days > _PROMPT_TRASH_RETENTION_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"`days` must be between 0 and {_PROMPT_TRASH_RETENTION_MAX}.",
        )
    existing = await db.get(AppSetting, _PROMPT_TRASH_RETENTION_KEY)
    if existing is None:
        db.add(AppSetting(key=_PROMPT_TRASH_RETENTION_KEY, value=days))
    else:
        existing.value = days
    await db.commit()
    try:
        from app.services.app_settings_cache import invalidate
        invalidate(_PROMPT_TRASH_RETENTION_KEY)
    except Exception:
        pass
    return {
        "days": days,
        "default": _PROMPT_TRASH_RETENTION_DEFAULT,
        "max": _PROMPT_TRASH_RETENTION_MAX,
    }


@router.get("/trash", response_model=PromptListResponse)
async def list_trashed_prompts(
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> PromptListResponse:
    stmt = (
        select(Prompt)
        .options(selectinload(Prompt.tags))
        .where(Prompt.deleted_at.is_not(None))
    )
    count_stmt = select(func.count(Prompt.id)).where(
        Prompt.deleted_at.is_not(None)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Prompt.name.ilike(like))
        count_stmt = count_stmt.where(Prompt.name.ilike(like))
    total = int((await db.execute(count_stmt)).scalar_one())
    stmt = (
        stmt.order_by(Prompt.deleted_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).unique().scalars().all()
    users = await _user_lookup(db, [r.created_by_id for r in rows])
    items: list[PromptListItem] = []
    for p in rows:
        cv = p.current_version
        cv_field: PromptVersionRead | None = None
        if cv is not None:
            cv_users = await _user_lookup(db, [cv.created_by_id])
            cv_field = PromptVersionRead(
                id=cv.id,
                version_number=cv.version_number,
                content=cv.content,
                change_note=cv.change_note,
                created_by_id=cv.created_by_id,
                created_at=cv.created_at,
                **_user_fields(cv.created_by_id, cv_users),
            )
        items.append(
            PromptListItem(
                id=p.id,
                name=p.name,
                category_id=p.category_id,
                current_version=cv_field,
                tags=p.tags,
                created_by_id=p.created_by_id,
                created_at=p.created_at,
                updated_at=p.updated_at,
                deleted_at=p.deleted_at,
                **_user_fields(p.created_by_id, users),
            )
        )
    return PromptListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/trash/{prompt_id}", response_model=PromptDetail)
async def preview_trashed_prompt(
    prompt_id: int, db: AsyncSession = Depends(get_db)
) -> PromptDetail:
    """Read-only preview of a trashed prompt — its content + version history."""
    p = await _get_trashed_prompt_or_404(db, prompt_id)
    # Reuse the same _detail builder as the active surface.
    return await _to_detail_with_users(db, p)


@router.post("/{prompt_id}/restore", response_model=PromptDetail)
async def restore_prompt(
    prompt_id: int, db: AsyncSession = Depends(get_db)
) -> PromptDetail:
    """Restore a trashed prompt to the active list.

    If the prompt's original category has been deleted in the meantime,
    it's restored uncategorized (`category_id=NULL`) so the FK doesn't
    break. Tags and version history are unchanged.
    """
    p = await _get_trashed_prompt_or_404(db, prompt_id)
    if p.category_id is not None:
        cat = await db.get(Category, p.category_id)
        if cat is None:
            p.category_id = None
    p.deleted_at = None
    await db.commit()
    # Commit expires all attributes; the lazy="joined" current_version
    # would otherwise fire a sync I/O during _to_detail_with_users and
    # crash under the async session. Re-load with the eager paths.
    fresh = await _get_prompt_or_404(db, p.id, include_trashed=True)
    return await _to_detail_with_users(db, fresh)


@router.delete(
    "/{prompt_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def permanently_delete_prompt(
    prompt_id: int, db: AsyncSession = Depends(get_db)
) -> Response:
    """Hard-delete a trashed prompt — version history is gone forever.

    bulk_table_columns.prompt_id is SET NULL on cascade, so the column
    keeps existing with no prompt reference. Saved generations + bulk
    cells keep their stored text (snapshot, not a live reference).
    """
    p = await _get_trashed_prompt_or_404(db, prompt_id)
    # Break the FK from prompts.current_version_id before deleting so the
    # cascade on prompt_versions can run cleanly.
    p.current_version_id = None
    await db.flush()
    await db.delete(p)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/trash", response_model=dict)
async def empty_trash(db: AsyncSession = Depends(get_db)) -> dict:
    rows = (
        await db.execute(
            select(Prompt).where(Prompt.deleted_at.is_not(None))
        )
    ).scalars().all()
    for p in rows:
        p.current_version_id = None
    if rows:
        await db.flush()
    for p in rows:
        await db.delete(p)
    await db.commit()
    return {"deleted": len(rows)}


@router.post("/trash/bulk-restore", response_model=dict)
async def bulk_restore_prompts(
    payload: TrashBulkIds, db: AsyncSession = Depends(get_db)
) -> dict:
    rows = (
        await db.execute(
            select(Prompt).where(
                Prompt.id.in_(payload.ids), Prompt.deleted_at.is_not(None)
            )
        )
    ).scalars().all()
    for p in rows:
        if p.category_id is not None:
            cat = await db.get(Category, p.category_id)
            if cat is None:
                p.category_id = None
        p.deleted_at = None
    await db.commit()
    return {"restored": len(rows)}


@router.delete("/trash/bulk", response_model=dict)
async def bulk_permanent_delete_prompts(
    payload: TrashBulkIds, db: AsyncSession = Depends(get_db)
) -> dict:
    rows = (
        await db.execute(
            select(Prompt).where(
                Prompt.id.in_(payload.ids), Prompt.deleted_at.is_not(None)
            )
        )
    ).scalars().all()
    for p in rows:
        p.current_version_id = None
    if rows:
        await db.flush()
    for p in rows:
        await db.delete(p)
    await db.commit()
    return {"deleted": len(rows)}


@router.get("/{prompt_id}", response_model=PromptDetail)
async def get_prompt(prompt_id: int, db: AsyncSession = Depends(get_db)) -> PromptDetail:
    p = await _get_prompt_or_404(db, prompt_id)
    return await _to_detail_with_users(db, p)


# ---------- create ----------

@router.post("", response_model=PromptDetail, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    payload: PromptCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptDetail:
    if payload.category_id is not None:
        await _verify_category(db, payload.category_id)
    tags = await _resolve_tags(db, payload.tag_ids)

    p = Prompt(
        name=payload.name.strip(),
        category_id=payload.category_id,
        created_by_id=actor.id,
    )
    p.tags = tags
    db.add(p)
    await db.flush()  # assigns p.id

    v = PromptVersion(
        prompt_id=p.id,
        version_number=1,
        content=payload.content,
        change_note=payload.change_note,
        created_by_id=actor.id,
    )
    db.add(v)
    await db.flush()  # assigns v.id

    p.current_version_id = v.id
    await db.commit()

    fresh = await _get_prompt_or_404(db, p.id)
    return await _to_detail_with_users(db, fresh)


# ---------- update metadata only ----------

@router.patch("/{prompt_id}", response_model=PromptDetail)
async def update_prompt_meta(
    prompt_id: int,
    payload: PromptMetaUpdate,
    db: AsyncSession = Depends(get_db),
) -> PromptDetail:
    p = await _get_prompt_or_404(db, prompt_id)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"]:
        p.name = data["name"].strip()
    if "category_id" in data:
        if data["category_id"] is not None:
            await _verify_category(db, data["category_id"])
        p.category_id = data["category_id"]
    if "tag_ids" in data and data["tag_ids"] is not None:
        p.tags = await _resolve_tags(db, data["tag_ids"])

    await db.commit()
    fresh = await _get_prompt_or_404(db, p.id)
    return await _to_detail_with_users(db, fresh)


# ---------- new version (edit content) ----------

@router.post("/{prompt_id}/versions", response_model=PromptDetail, status_code=status.HTTP_201_CREATED)
async def create_new_version(
    prompt_id: int,
    payload: PromptVersionCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptDetail:
    p = await _get_prompt_or_404(db, prompt_id)
    next_n = await _next_version_number(db, p.id)
    v = PromptVersion(
        prompt_id=p.id,
        version_number=next_n,
        content=payload.content,
        change_note=payload.change_note,
        created_by_id=actor.id,
    )
    db.add(v)
    await db.flush()
    p.current_version_id = v.id
    await db.commit()
    fresh = await _get_prompt_or_404(db, p.id)
    return await _to_detail_with_users(db, fresh)


# ---------- revert ----------

@router.post("/{prompt_id}/revert", response_model=PromptDetail)
async def revert_prompt(
    prompt_id: int,
    payload: PromptRevert,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptDetail:
    p = await _get_prompt_or_404(db, prompt_id)
    target = next(
        (v for v in p.versions if v.version_number == payload.target_version_number),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No version {payload.target_version_number} for this prompt",
        )

    next_n = await _next_version_number(db, p.id)
    note = (
        payload.change_note
        or f"Reverted to v{payload.target_version_number}"
    )
    v = PromptVersion(
        prompt_id=p.id,
        version_number=next_n,
        content=target.content,
        change_note=note,
        created_by_id=actor.id,
    )
    db.add(v)
    await db.flush()
    p.current_version_id = v.id
    await db.commit()
    fresh = await _get_prompt_or_404(db, p.id)
    return await _to_detail_with_users(db, fresh)


# ---------- edit just the change_note on an existing version ----------

@router.patch(
    "/{prompt_id}/versions/{version_number}/note",
    response_model=PromptDetail,
    summary="Edit the change note on an existing version (does not create a new version).",
)
async def edit_version_note(
    prompt_id: int,
    version_number: int,
    payload: PromptVersionNoteUpdate,
    db: AsyncSession = Depends(get_db),
) -> PromptDetail:
    p = await _get_prompt_or_404(db, prompt_id)
    target = next(
        (v for v in p.versions if v.version_number == version_number),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No version {version_number}"
        )
    target.change_note = payload.change_note
    await db.commit()
    fresh = await _get_prompt_or_404(db, p.id)
    return await _to_detail_with_users(db, fresh)


# ---------- get a specific version ----------

@router.get(
    "/{prompt_id}/versions/{version_number}",
    response_model=PromptDetail,
    summary="Returns the prompt with current_version overridden to the requested version (for diffing/preview).",
)
async def get_prompt_at_version(
    prompt_id: int, version_number: int, db: AsyncSession = Depends(get_db)
) -> PromptDetail:
    p = await _get_prompt_or_404(db, prompt_id)
    target = next(
        (v for v in p.versions if v.version_number == version_number),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No version {version_number}"
        )
    detail = await _to_detail_with_users(db, p)
    # Override current_version with the requested one for this response.
    users = await _user_lookup(db, [target.created_by_id])
    detail.current_version = PromptVersionRead(
        id=target.id,
        version_number=target.version_number,
        content=target.content,
        change_note=target.change_note,
        created_by_id=target.created_by_id,
        created_at=target.created_at,
        **_user_fields(target.created_by_id, users),
    )
    detail.variables = extract_variables(target.content)
    return detail


# ---------- delete (soft) + trash surface ----------

@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(prompt_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """Move a prompt to Trash (soft-delete).

    The version history is preserved intact until permanent deletion.
    Existing bulk_table_columns that referenced this prompt KEEP working
    (the column's `prompt_id` is unaffected by soft-delete) — but new
    generation runs can't pick up trashed prompts because the active list
    filters `deleted_at IS NULL`.
    """
    p = await _get_prompt_or_404(db, prompt_id)
    p.deleted_at = datetime.now(timezone.utc)
    await db.commit()


