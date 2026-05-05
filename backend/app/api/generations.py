"""CRUD for user-saved Single-mode generations.

Per-user visibility: each user sees only their own saves. Admins are NOT given
"see-all" yet — keeping the model simple. Easy to relax later if needed.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Generation, Prompt, User
from app.db.session import get_db
from app.schemas.generation import (
    SaveGenerationRequest,
    SavedGenerationListItem,
    SavedGenerationRead,
    SavedGenerationRenameRequest,
)

router = APIRouter(
    prefix="/generations",
    tags=["generations"],
    dependencies=[Depends(get_current_user)],
)


async def _get_owned_or_404(
    db: AsyncSession, gen_id: int, actor: User
) -> Generation:
    g = (
        await db.execute(select(Generation).where(Generation.id == gen_id))
    ).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if g.created_by_id != actor.id:
        # Don't reveal that it exists for someone else; treat as not found.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return g


@router.get("", response_model=list[SavedGenerationListItem])
async def list_my_generations(
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
) -> list[Generation]:
    rows = (
        await db.execute(
            select(Generation)
            .where(Generation.created_by_id == actor.id)
            .order_by(Generation.created_at.desc())
            .limit(min(limit, 500))
        )
    ).scalars().all()
    return list(rows)


@router.get("/{gen_id}", response_model=SavedGenerationRead)
async def get_generation(
    gen_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Generation:
    return await _get_owned_or_404(db, gen_id, actor)


@router.post("", response_model=SavedGenerationRead, status_code=status.HTTP_201_CREATED)
async def save_generation(
    payload: SaveGenerationRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Generation:
    # Snapshot the prompt name so the saved record is meaningful even after delete.
    prompt = (
        await db.execute(select(Prompt).where(Prompt.id == payload.prompt_id))
    ).scalar_one_or_none()
    name_snapshot = prompt.name if prompt else f"(prompt #{payload.prompt_id})"

    name = payload.name or _default_name(name_snapshot)

    g = Generation(
        name=name,
        prompt_id=payload.prompt_id if prompt else None,
        prompt_version_number=payload.prompt_version_number,
        prompt_name_snapshot=name_snapshot,
        rendered_prompt=payload.rendered_prompt,
        output=payload.output,
        variables=payload.variables,
        provider_code=payload.provider_code,
        model_used=payload.model_used,
        finish_reason=payload.finish_reason,
        created_by_id=actor.id,
    )
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return g


@router.patch("/{gen_id}", response_model=SavedGenerationRead)
async def rename_generation(
    gen_id: int,
    payload: SavedGenerationRenameRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Generation:
    g = await _get_owned_or_404(db, gen_id, actor)
    g.name = payload.name.strip()
    await db.commit()
    await db.refresh(g)
    return g


@router.delete("/{gen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_generation(
    gen_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    g = await _get_owned_or_404(db, gen_id, actor)
    await db.delete(g)
    await db.commit()


def _default_name(prompt_name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return f"{prompt_name} · {ts}"
