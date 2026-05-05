from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sqla_delete
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Prompt, Tag, prompt_tags
from app.db.session import get_db
from app.schemas.tag import (
    TagCreate,
    TagListResponse,
    TagMergeRequest,
    TagRead,
    TagUpdate,
    TagWithStats,
)

router = APIRouter(
    prefix="/tags", tags=["tags"], dependencies=[Depends(get_current_user)]
)


# ---- list (picker, unchanged shape so all pickers keep working) ----

@router.get("", response_model=list[TagRead])
async def list_tags(db: AsyncSession = Depends(get_db)) -> list[Tag]:
    return list((await db.execute(select(Tag).order_by(Tag.name))).scalars().all())


# ---- list with stats + pagination (for the management page) ----

@router.get("/manage", response_model=TagListResponse)
async def list_tags_for_management(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> TagListResponse:
    """Tag listing with prompt-count and last-used time, paginated.

    The "stats" subquery left-joins through prompt_tags + prompts so unused tags
    (no prompts referencing them) show up with prompt_count=0 and last_used=null.
    """
    base = (
        select(
            Tag.id,
            Tag.name,
            Tag.created_at,
            func.count(Prompt.id).label("prompt_count"),
            func.max(Prompt.updated_at).label("last_used"),
        )
        .outerjoin(prompt_tags, prompt_tags.c.tag_id == Tag.id)
        .outerjoin(Prompt, Prompt.id == prompt_tags.c.prompt_id)
        .group_by(Tag.id)
    )

    count_stmt = select(func.count(Tag.id))

    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        base = base.where(Tag.name.ilike(like))
        count_stmt = count_stmt.where(Tag.name.ilike(like))

    total = int((await db.execute(count_stmt)).scalar_one())

    base = (
        base.order_by(Tag.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(base)).all()

    items = [
        TagWithStats(
            id=row.id,
            name=row.name,
            prompt_count=int(row.prompt_count or 0),
            last_used=row.last_used,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return TagListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagCreate, db: AsyncSession = Depends(get_db)) -> Tag:
    name = payload.name.strip().lower()
    tag = Tag(name=name)
    db.add(tag)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(select(Tag).where(Tag.name == name))
        ).scalar_one()
        return existing
    await db.refresh(tag)
    return tag


@router.patch("/{tag_id}", response_model=TagRead)
async def rename_tag(
    tag_id: int,
    payload: TagUpdate,
    db: AsyncSession = Depends(get_db),
) -> Tag:
    tag = (
        await db.execute(select(Tag).where(Tag.id == tag_id))
    ).scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    new_name = payload.name.strip().lower()
    if new_name == tag.name:
        return tag
    tag.name = new_name
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A tag named '{new_name}' already exists. Use Merge to combine them.",
        )
    await db.refresh(tag)
    return tag


@router.post("/{tag_id}/merge", response_model=TagRead)
async def merge_tag(
    tag_id: int,
    payload: TagMergeRequest,
    db: AsyncSession = Depends(get_db),
) -> Tag:
    """Move every prompt currently tagged with `tag_id` onto `target_id` instead,
    then delete `tag_id`. The target tag is returned.

    Race-tolerant: the prompt_tags PK is composite (prompt_id, tag_id), so two
    prompts already both tagged with src + target wouldn't blow up — we use
    INSERT ... ON CONFLICT DO NOTHING, then delete the src rows.
    """
    if tag_id == payload.target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge a tag into itself.",
        )

    src = (await db.execute(select(Tag).where(Tag.id == tag_id))).scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source tag not found")
    target = (
        await db.execute(select(Tag).where(Tag.id == payload.target_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Target tag not found"
        )

    # 1. For every prompt tagged with src, ensure it's also tagged with target.
    prompt_ids = (
        await db.execute(
            select(prompt_tags.c.prompt_id).where(prompt_tags.c.tag_id == src.id)
        )
    ).scalars().all()
    if prompt_ids:
        stmt = pg_insert(prompt_tags).values(
            [{"prompt_id": pid, "tag_id": target.id} for pid in prompt_ids]
        )
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["prompt_id", "tag_id"]
        )
        await db.execute(stmt)

    # 2. Drop every link to src.
    await db.execute(sqla_delete(prompt_tags).where(prompt_tags.c.tag_id == src.id))

    # 3. Delete the now-orphan src tag itself.
    await db.delete(src)
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db)) -> None:
    tag = (await db.execute(select(Tag).where(Tag.id == tag_id))).scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    await db.delete(tag)
    await db.commit()
