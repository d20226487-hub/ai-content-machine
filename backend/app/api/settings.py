import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.crypto import decrypt, encrypt
from app.db.models import Provider
from app.db.session import get_db
from app.providers.base import GenerationParams, ProviderError
from app.providers.registry import PROVIDERS
from app.schemas.provider import (
    ConnectionTestRequest,
    ConnectionTestResult,
    ProviderRead,
    ProviderUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_role("admin"))])


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(db: AsyncSession = Depends(get_db)) -> list[Provider]:
    rows = (await db.execute(select(Provider).order_by(Provider.id))).scalars().all()
    # Pydantic uses the `has_api_key` @property to populate the response.
    return list(rows)


@router.get("/providers/{code}", response_model=ProviderRead)
async def get_provider(code: str, db: AsyncSession = Depends(get_db)) -> Provider:
    provider = await _get_or_404(db, code)
    return provider


@router.patch("/providers/{code}", response_model=ProviderRead)
async def update_provider(
    code: str,
    payload: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
) -> Provider:
    provider = await _get_or_404(db, code)

    # Only update fields the client actually sent (Pydantic v2: exclude_unset).
    data = payload.model_dump(exclude_unset=True)

    if "api_key" in data:
        raw = data.pop("api_key")
        if raw == "":
            provider.api_key_encrypted = None
        elif raw is not None:
            provider.api_key_encrypted = encrypt(raw)
        # if raw is None and field was sent, leave unchanged (treat as no-op)

    for field, value in data.items():
        setattr(provider, field, value)

    await db.commit()
    await db.refresh(provider)
    return provider


@router.post("/providers/{code}/test", response_model=ConnectionTestResult)
async def test_provider_connection(
    code: str,
    payload: ConnectionTestRequest,
    db: AsyncSession = Depends(get_db),
) -> ConnectionTestResult:
    """Send a tiny request through the provider to verify the API key works.

    Failures return ok=false (HTTP 200) with the error message — the UI can
    display it inline without any error-handling boilerplate.
    """
    provider = await _get_or_404(db, code)

    cls = PROVIDERS.get(code)
    if cls is None:
        return ConnectionTestResult(
            ok=False,
            provider_code=code,
            error=(
                f"Provider '{code}' is recognized but not implemented yet — "
                "only the providers in app/providers/registry.py can be tested."
            ),
        )

    # Use the typed key if provided, otherwise decrypt the stored one.
    key: str | None = payload.api_key or None
    if not key:
        if not provider.api_key_encrypted:
            return ConnectionTestResult(
                ok=False,
                provider_code=code,
                error="No API key set. Type one above or save one first.",
            )
        try:
            key = decrypt(provider.api_key_encrypted)
        except Exception as e:
            return ConnectionTestResult(
                ok=False,
                provider_code=code,
                error=f"Failed to decrypt stored key (FERNET_KEY may have been rotated): {e}",
            )

    model = payload.model or provider.default_model
    if not model:
        return ConnectionTestResult(
            ok=False,
            provider_code=code,
            error="No model specified and no default_model configured.",
        )

    instance = cls(api_key=key, default_model=model)
    started = time.monotonic()
    try:
        result = await instance.generate(
            prompt="Reply with the single word: pong",
            model=model,
            params=GenerationParams(max_output_tokens=20, temperature=0),
        )
    except ProviderError as e:
        return ConnectionTestResult(
            ok=False,
            provider_code=code,
            model_used=model,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=str(e),
        )
    except Exception as e:  # last-resort net to keep the API call shape consistent
        return ConnectionTestResult(
            ok=False,
            provider_code=code,
            model_used=model,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=f"Unexpected error: {e}",
        )

    snippet = (result.text or "").strip()[:120]
    return ConnectionTestResult(
        ok=True,
        provider_code=code,
        model_used=result.model,
        latency_ms=int((time.monotonic() - started) * 1000),
        sample_output=snippet,
    )


async def _get_or_404(db: AsyncSession, code: str) -> Provider:
    provider = (
        await db.execute(select(Provider).where(Provider.code == code))
    ).scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{code}' not found",
        )
    return provider
