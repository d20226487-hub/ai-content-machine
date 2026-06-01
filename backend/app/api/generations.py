"""CRUD for user-saved Single-mode generations.

Per-user visibility: each user sees only their own saves. Admins are NOT given
"see-all" yet — keeping the model simple. Easy to relax later if needed.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Generation, Prompt, User
from app.db.session import get_db
from app.schemas.generation import (
    SaveGenerationRequest,
    SavedGenerationListItem,
    SavedGenerationListResponse,
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


@router.get("", response_model=SavedGenerationListResponse)
async def list_my_generations(
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    q: str | None = Query(default=None),
) -> SavedGenerationListResponse:
    """The signed-in user's saved generations, newest first. Optional ``q``
    matches the save name OR the snapshotted prompt name (case-insensitive)."""
    base = select(Generation).where(Generation.created_by_id == actor.id)
    if q and q.strip():
        pat = f"%{q.strip()}%"
        base = base.where(
            or_(
                Generation.name.ilike(pat),
                Generation.prompt_name_snapshot.ilike(pat),
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        (
            await db.execute(
                base.order_by(Generation.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return SavedGenerationListResponse(
        items=[SavedGenerationListItem.model_validate(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


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


@router.post("/{gen_id}/translate", response_model=dict)
async def translate_generation(
    gen_id: int,
    payload: dict,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Translate a saved generation's `output` using the brain prompt.

    Body: ``{"target_language": "ru", "force": false}``. Result is
    memoized on ``generations.translations[<lang>]`` so the next open
    is free. ``force=true`` bypasses the cache for a fresh LLM run.
    """
    from app.providers.base import ProviderError as _ProviderError
    from app.providers.registry import ProviderNotConfigured as _ProviderNotConfigured
    from app.services.brain import (
        cache_lookup as _cache_lookup,
        make_translation_entry as _make_entry,
        resolve_target_language as _resolve_lang,
        translate_text as _translate_text,
    )

    g = await _get_owned_or_404(db, gen_id, actor)
    if not (g.output and g.output.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generation has no output to translate.",
        )

    requested = await _resolve_lang(db, payload.get("target_language"))
    force = bool(payload.get("force"))

    if not force:
        cached = _cache_lookup(g.translations, requested)
        if cached is not None:
            return {
                "target_language": requested,
                "cached": True,
                **cached,
            }

    try:
        text, code, model = await _translate_text(
            db, source_text=g.output, target_language=requested
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
                "endpoint": "/generations/.../translate",
                "generation_id": gen_id,
                "target_language": requested,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )

    entry = _make_entry(text=text, provider_code=code, model=model)
    next_translations = dict(g.translations or {})
    next_translations[requested] = entry
    g.translations = next_translations
    await db.commit()

    from app.services.usage import record_usage

    await record_usage(
        db,
        user_id=actor.id,
        provider_code=code,
        model=model,
        prompt_tokens=None,
        completion_tokens=None,
        source="brain_translate",
        source_ref={"generation_id": gen_id, "target_language": requested},
    )

    return {"target_language": requested, "cached": False, **entry}


def _default_name(prompt_name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return f"{prompt_name} · {ts}"
