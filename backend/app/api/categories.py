from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Category, Prompt, User
from app.db.session import get_db
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
    dependencies=[Depends(get_current_user)],
)


async def _get_or_404(db: AsyncSession, category_id: int) -> Category:
    cat = (
        await db.execute(select(Category).where(Category.id == category_id))
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return cat


async def _would_create_cycle(
    db: AsyncSession, category_id: int, new_parent_id: int | None
) -> bool:
    """Walk up from new_parent_id; if we hit category_id, it would create a cycle."""
    if new_parent_id is None:
        return False
    cursor = new_parent_id
    seen: set[int] = set()
    while cursor is not None:
        if cursor == category_id:
            return True
        if cursor in seen:
            return True
        seen.add(cursor)
        parent = (
            await db.execute(select(Category.parent_id).where(Category.id == cursor))
        ).scalar_one_or_none()
        cursor = parent
    return False


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    with_counts: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryRead]:
    """List every category. With `with_counts=true`, augment each row with the
    number of prompts directly in that folder (`prompt_count`) and the number
    of direct subfolders (`subfolder_count`). Useful for the Drive-style view.
    """
    rows = list(
        (await db.execute(select(Category).order_by(Category.name))).scalars().all()
    )
    if not with_counts:
        return [CategoryRead.model_validate(c) for c in rows]

    # Direct prompt count per category (LEFT JOIN-ish via aggregate)
    prompt_counts = dict(
        (
            await db.execute(
                select(Prompt.category_id, func.count(Prompt.id))
                .where(Prompt.category_id.is_not(None))
                .group_by(Prompt.category_id)
            )
        ).all()
    )
    # Direct subfolder count per category (categories whose parent_id == this id)
    subfolder_counts = dict(
        (
            await db.execute(
                select(Category.parent_id, func.count(Category.id))
                .where(Category.parent_id.is_not(None))
                .group_by(Category.parent_id)
            )
        ).all()
    )
    out: list[CategoryRead] = []
    for c in rows:
        cr = CategoryRead.model_validate(c)
        cr.prompt_count = int(prompt_counts.get(c.id, 0))
        cr.subfolder_count = int(subfolder_counts.get(c.id, 0))
        out.append(cr)
    return out


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Category:
    if payload.parent_id is not None:
        await _get_or_404(db, payload.parent_id)
    cat = Category(
        name=payload.name.strip(),
        parent_id=payload.parent_id,
        created_by_id=actor.id,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> Category:
    cat = await _get_or_404(db, category_id)
    data = payload.model_dump(exclude_unset=True)

    if "parent_id" in data:
        new_parent = data["parent_id"]
        if new_parent is not None:
            await _get_or_404(db, new_parent)
        if await _would_create_cycle(db, category_id, new_parent):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Move would create a cycle in the category tree",
            )
        cat.parent_id = new_parent

    if "name" in data and data["name"] is not None:
        cat.name = data["name"].strip()

    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)) -> None:
    cat = await _get_or_404(db, category_id)
    try:
        await db.delete(cat)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Category is not empty. Move its prompts and subcategories elsewhere "
                "before deleting."
            ),
        )
