"""Brain — configurable system prompts for on-demand actions.

Today the only configurable surface is `translate`, used by the Translate
button in the bulk-table cell editor. The shape supports adding more
prompts (Summarize, Title-suggest, etc.) without another migration.

Endpoints:
  GET  /brain/prompts            — return all brain prompts (any role)
  PUT  /brain/prompts/translate  — admin only; update translate config

Cell-level translate runs live in ``library.py`` next to the rest of the
cell endpoints because they enforce the same table-ACL.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.models import User
from app.db.session import get_db
from app.providers.base import ProviderError
from app.providers.registry import ProviderNotConfigured
from app.services.brain import (
    load_brain,
    now_iso,
    resolve_target_language,
    save_fix_links_config,
    save_gdocs_meta_config,
    save_gdocs_pairing_config,
    save_translate_config,
    translate_text,
)
from app.services.error_log import log_error
from app.services.usage import record_usage

router = APIRouter(
    prefix="/brain", tags=["brain"], dependencies=[Depends(get_current_user)]
)


class TranslatePromptRead(BaseModel):
    prompt: str
    provider_code: str | None = None
    model: str | None = None
    default_target_language: str = "ru"


class FixLinksPromptRead(BaseModel):
    prompt: str
    provider_code: str | None = None
    model: str | None = None


class GdocsMetaPromptRead(BaseModel):
    # Prompt only — the Google-Docs import job picks its provider/model on the
    # upload modal, so there is nothing to configure here besides the prompt.
    prompt: str


class GdocsPairingPromptRead(BaseModel):
    # Prompt only — maps each imported Doc to its Structure entry (slug source).
    prompt: str


class BrainPromptsRead(BaseModel):
    translate: TranslatePromptRead
    fix_links: FixLinksPromptRead
    gdocs_meta: GdocsMetaPromptRead
    gdocs_pairing: GdocsPairingPromptRead


class TranslatePromptUpdate(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)
    provider_code: str | None = None
    model: str | None = None
    default_target_language: str = Field(
        default="ru", min_length=2, max_length=16
    )


class FixLinksPromptUpdate(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)
    provider_code: str | None = None
    model: str | None = None


class GdocsMetaPromptUpdate(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)


class GdocsPairingPromptUpdate(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)


@router.get("/prompts", response_model=BrainPromptsRead)
async def get_prompts(db: AsyncSession = Depends(get_db)) -> BrainPromptsRead:
    cfg = await load_brain(db)
    return BrainPromptsRead.model_validate(cfg)


@router.put("/prompts/translate", response_model=TranslatePromptRead)
async def update_translate(
    payload: TranslatePromptUpdate,
    actor: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> TranslatePromptRead:
    out = await save_translate_config(
        db,
        prompt=payload.prompt,
        provider_code=payload.provider_code,
        model=payload.model,
        default_target_language=payload.default_target_language,
        actor_id=actor.id,
    )
    return TranslatePromptRead.model_validate(out)


@router.put("/prompts/fix-links", response_model=FixLinksPromptRead)
async def update_fix_links(
    payload: FixLinksPromptUpdate,
    actor: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> FixLinksPromptRead:
    out = await save_fix_links_config(
        db,
        prompt=payload.prompt,
        provider_code=payload.provider_code,
        model=payload.model,
        actor_id=actor.id,
    )
    return FixLinksPromptRead.model_validate(out)


@router.put("/prompts/gdocs-meta", response_model=GdocsMetaPromptRead)
async def update_gdocs_meta(
    payload: GdocsMetaPromptUpdate,
    actor: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> GdocsMetaPromptRead:
    out = await save_gdocs_meta_config(
        db, prompt=payload.prompt, actor_id=actor.id
    )
    return GdocsMetaPromptRead.model_validate(out)


@router.put("/prompts/gdocs-pairing", response_model=GdocsPairingPromptRead)
async def update_gdocs_pairing(
    payload: GdocsPairingPromptUpdate,
    actor: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> GdocsPairingPromptRead:
    out = await save_gdocs_pairing_config(
        db, prompt=payload.prompt, actor_id=actor.id
    )
    return GdocsPairingPromptRead.model_validate(out)


class TranslateTextRequest(BaseModel):
    """Stateless translate — used by surfaces that don't have a stable
    entity id to memoize against (test-modal results, unsaved single
    drafts). The text is sent inline; nothing is persisted."""

    text: str = Field(min_length=1, max_length=100_000)
    target_language: str | None = None


class TranslateTextResponse(BaseModel):
    text: str
    provider_used: str | None = None
    model_used: str | None = None
    translated_at: str
    target_language: str
    # Always false — the stateless endpoint never serves a cached entry.
    # Kept for shape parity with the memoized endpoints so the frontend
    # adapter doesn't have to branch.
    cached: bool = False


@router.post("/translate-text", response_model=TranslateTextResponse)
async def translate_raw_text(
    payload: TranslateTextRequest,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TranslateTextResponse:
    """Translate arbitrary text using the brain prompt. Stateless —
    no memoization. Used by ephemeral surfaces (test-modal output,
    unsaved single draft) where there is no entity to cache against."""
    if not payload.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to translate.",
        )

    requested = await resolve_target_language(db, payload.target_language)

    try:
        text, code, model = await translate_text(
            db, source_text=payload.text, target_language=requested
        )
    except ProviderNotConfigured as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except ProviderError as e:
        await log_error(
            db,
            source="api",
            category="provider_error",
            message=str(e),
            user_id=actor.id,
            status_code=getattr(e, "status_code", None),
            context={
                "endpoint": "/brain/translate-text",
                "target_language": requested,
                "text_len": len(payload.text),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )

    await record_usage(
        db,
        user_id=actor.id,
        provider_code=code,
        model=model,
        prompt_tokens=None,
        completion_tokens=None,
        source="brain_translate",
        source_ref={"target_language": requested, "kind": "raw_text"},
    )

    return TranslateTextResponse(
        text=text,
        provider_used=code,
        model_used=model,
        translated_at=now_iso(),
        target_language=requested,
        cached=False,
    )
