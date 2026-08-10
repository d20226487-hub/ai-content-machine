from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Prompt, PromptVersion
from app.db.session import get_db
from app.providers.base import GenerationParams, ProviderError
from app.providers.registry import ProviderNotConfigured, get_provider
from app.schemas.generation import (
    GenerateSingleRequest,
    GenerateSingleResponse,
    RenderPromptRequest,
    RenderPromptResponse,
)
from app.db.models import Provider
from app.services.ai_assist import first_enabled_provider_code
from app.services.error_log import log_error
from app.services.prompts import extract_variables, render_template
from app.services.provider_cache import get_enabled_providers
from app.services.usage import record_usage

router = APIRouter(
    prefix="/generate", tags=["generate"], dependencies=[Depends(get_current_user)]
)


from pydantic import BaseModel


class EnabledProvider(BaseModel):
    code: str
    display_name: str
    default_model: str | None
    available_models: list[str]
    has_api_key: bool  # if false, the dropdown should disable this option


@router.get("/providers", response_model=list[EnabledProvider])
async def list_enabled_providers(
    db: AsyncSession = Depends(get_db),
) -> list[EnabledProvider]:
    """Every provider toggled ON in Settings, regardless of whether a key is set yet.
    The frontend disables options where has_api_key=false so the user understands
    why an enabled provider isn't selectable.

    Backed by a 15s in-process TTL cache; settings.py PATCH/test routes call
    invalidate() so an admin's own session sees changes immediately. Other
    workers see them on the next TTL boundary."""
    snapshot = await get_enabled_providers(db)
    return [
        EnabledProvider(
            code=p.code,
            display_name=p.display_name,
            default_model=p.default_model,
            available_models=list(p.available_models),
            has_api_key=p.has_api_key,
        )
        for p in snapshot
    ]


async def _load_version(
    db: AsyncSession, prompt_id: int, version_number: int | None
) -> tuple[Prompt, PromptVersion]:
    prompt = (
        await db.execute(select(Prompt).where(Prompt.id == prompt_id))
    ).scalar_one_or_none()
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")

    if version_number is None:
        # Use the prompt's current version.
        if prompt.current_version_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt has no current version"
            )
        version = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.id == prompt.current_version_id)
            )
        ).scalar_one()
    else:
        version = (
            await db.execute(
                select(PromptVersion).where(
                    PromptVersion.prompt_id == prompt_id,
                    PromptVersion.version_number == version_number,
                )
            )
        ).scalar_one_or_none()
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_number} not found",
            )

    return prompt, version


@router.post("/render", response_model=RenderPromptResponse)
async def render_prompt(
    payload: RenderPromptRequest, db: AsyncSession = Depends(get_db)
) -> RenderPromptResponse:
    """Resolve variables against the prompt's content. No AI call."""
    _, version = await _load_version(db, payload.prompt_id, payload.version_number)
    rendered, missing = render_template(version.content, payload.variables)
    return RenderPromptResponse(
        rendered_prompt=rendered,
        expected_variables=extract_variables(version.content),
        missing_variables=missing,
    )


@router.post("/single", response_model=GenerateSingleResponse)
async def generate_single(
    payload: GenerateSingleRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> GenerateSingleResponse:
    _, version = await _load_version(db, payload.prompt_id, payload.version_number)
    rendered, missing = render_template(version.content, payload.variables)

    code = payload.provider_code or await first_enabled_provider_code(db)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No AI provider is enabled. Configure one in Settings first.",
        )

    try:
        provider = await get_provider(db, code)
    except ProviderNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Grounding only works on the Vertex Gemini path (the only place the Google
    # Search tool is wired). Mirrors the bulk-column rule in api/library.py, and
    # validates the EFFECTIVE model — resolving the provider default when the
    # request leaves it unset — so an unsupported combination is rejected up
    # front instead of silently returning an ungrounded answer.
    if payload.grounding:
        eff_model = (payload.model or "").strip().lower()
        if not eff_model:
            prov_row = (
                await db.execute(select(Provider).where(Provider.code == code))
            ).scalar_one_or_none()
            eff_model = (
                (prov_row.default_model or "").strip().lower() if prov_row else ""
            )
        if code != "vertex":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Grounding requires Google Vertex AI with a Gemini model. "
                    "Pick Vertex as the provider for this test run."
                ),
            )
        if eff_model.startswith("claude"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Grounding is a Gemini feature — pick a Gemini model, not Claude.",
            )

    try:
        result = await provider.generate(
            prompt=rendered,
            model=payload.model,
            params=GenerationParams(
                temperature=payload.temperature,
                max_output_tokens=payload.max_output_tokens,
                grounding=payload.grounding,
            ),
        )
    except ProviderError as e:
        await log_error(
            db,
            source="api",
            category="provider_error",
            message=str(e),
            user_id=getattr(user, "id", None),
            provider=code,
            status_code=getattr(e, "status_code", None),
            context={
                "endpoint": "/generate/single",
                "prompt_id": payload.prompt_id,
                "model": payload.model,
                "raw": getattr(e, "raw", None),
            },
            resource_type="prompt",
            resource_id=payload.prompt_id,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    # Track-only spend log (#9). Best-effort: never breaks the request.
    await record_usage(
        db,
        user_id=getattr(user, "id", None),
        provider_code=code,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        source="single",
        source_ref={
            "prompt_id": payload.prompt_id,
            "version_number": payload.version_number,
        },
    )
    # Flat per-request surcharge for the Google Search grounding tool — billed
    # separately from tokens, same as the bulk path. Best-effort.
    if payload.grounding:
        from app.services.usage import record_grounding_surcharge

        await record_grounding_surcharge(
            db,
            user_id=getattr(user, "id", None),
            provider_code=code,
            model=result.model,
            source_ref={
                "prompt_id": payload.prompt_id,
                "version_number": payload.version_number,
                "source": "test",
            },
        )

    return GenerateSingleResponse(
        text=result.text,
        rendered_prompt=rendered,
        provider_used=code,
        model_used=result.model,
        finish_reason=result.finish_reason,
        missing_variables=missing,
        grounding_sources=result.grounding,
    )
