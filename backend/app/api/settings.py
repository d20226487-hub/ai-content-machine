import json
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

# Keys inside extra_config whose values are secret. Stripped before sending
# the row to the client; kept inside the encrypted blob server-side.
_SECRET_EXTRA_KEYS: frozenset[str] = frozenset({"service_account_json"})
from app.schemas.usage import PricingTableRow, PricingTableUpdate
from app.services.pricing import load_pricing, save_pricing
from app.services.provider_cache import invalidate as invalidate_provider_cache
from app.db.models import User
from app.api.deps import get_current_user

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_role("admin"))])


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(db: AsyncSession = Depends(get_db)) -> list[ProviderRead]:
    rows = (await db.execute(select(Provider).order_by(Provider.id))).scalars().all()
    return [_to_read(r) for r in rows]


@router.get("/providers/{code}", response_model=ProviderRead)
async def get_provider(code: str, db: AsyncSession = Depends(get_db)) -> ProviderRead:
    provider = await _get_or_404(db, code)
    return _to_read(provider)


@router.patch("/providers/{code}", response_model=ProviderRead)
async def update_provider(
    code: str,
    payload: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProviderRead:
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

    if "extra_config" in data:
        incoming = data.pop("extra_config")
        provider.extra_config_encrypted = _merge_extra_config(
            provider.extra_config_encrypted, incoming
        )

    for field, value in data.items():
        setattr(provider, field, value)

    await db.commit()
    await db.refresh(provider)
    # Drop the read cache so the admin's next page load reflects the change
    # in this worker. Cross-worker propagation is bounded by the cache TTL.
    invalidate_provider_cache()
    return _to_read(provider)


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
    # Vertex AI is the one provider that can run without an api_key when
    # service-account JSON is configured in extra_config — its check
    # happens further down at the provider layer.
    key: str | None = payload.api_key or None
    if not key:
        if provider.api_key_encrypted:
            try:
                key = decrypt(provider.api_key_encrypted)
            except Exception as e:
                return ConnectionTestResult(
                    ok=False,
                    provider_code=code,
                    error=(
                        "Failed to decrypt stored key (FERNET_KEY may have "
                        f"been rotated): {e}"
                    ),
                )
        elif code != "vertex" or not provider.extra_config_encrypted:
            return ConnectionTestResult(
                ok=False,
                provider_code=code,
                error="No API key set. Type one above or save one first.",
            )
    # `key` may still be None here — only legal for Vertex with SA creds.
    key = key or ""

    model = payload.model or provider.default_model
    if not model:
        return ConnectionTestResult(
            ok=False,
            provider_code=code,
            error="No model specified and no default_model configured.",
        )

    # For providers with structured creds (Vertex AI): decrypt the stored
    # extra_config so the SA-JSON path can mint a token. Test-via-typed-key
    # mode doesn't support typing the extra fields inline — save first,
    # then test. Same convention as the original UI text below.
    extra_config = _decrypt_extra_or_empty(provider.extra_config_encrypted)
    instance = cls(api_key=key, default_model=model, extra_config=extra_config)
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


def _decrypt_extra_or_empty(blob: str | None) -> dict:
    """Decrypt + parse the Fernet JSON blob, returning {} on missing/corrupt.

    Mirrors ``providers.registry._decrypt_extra`` but lives here because
    the settings layer needs the same fallback shape for serialization.
    """
    if not blob:
        return {}
    try:
        return json.loads(decrypt(blob))
    except (ValueError, json.JSONDecodeError):
        return {}


def _merge_extra_config(current_blob: str | None, incoming: dict | None) -> str | None:
    """Merge ``incoming`` into the currently-stored extra_config and re-encrypt.

    Per-field semantics, matching api_key:
      * key omitted → field unchanged
      * value == "" → field cleared
      * value != "" → field set / overwritten
    Sending ``incoming={}`` clears every field (NULLs the column).
    """
    if incoming is None:
        return current_blob  # untouched
    if incoming == {}:
        return None  # explicit reset
    merged = _decrypt_extra_or_empty(current_blob)
    for k, v in incoming.items():
        if v == "" or v is None:
            merged.pop(k, None)
        else:
            merged[k] = v
    if not merged:
        return None
    return encrypt(json.dumps(merged))


def _to_read(p: Provider) -> ProviderRead:
    """Serialize a Provider row, stripping secret fields from extra_config."""
    extra = _decrypt_extra_or_empty(p.extra_config_encrypted)
    public = {k: v for k, v in extra.items() if k not in _SECRET_EXTRA_KEYS}
    return ProviderRead(
        id=p.id,
        code=p.code,
        display_name=p.display_name,
        enabled=p.enabled,
        has_api_key=p.has_api_key,
        has_extra_config=p.has_extra_config,
        extra_config_public=public,
        default_model=p.default_model,
        prompt_creation_model=p.prompt_creation_model,
        available_models=list(p.available_models or []),
        requests_per_minute=p.requests_per_minute,
        max_concurrency=p.max_concurrency,
        batch_size=p.batch_size,
        inter_request_delay_ms=p.inter_request_delay_ms,
        retry_max_attempts=p.retry_max_attempts,
        backoff_base_ms=p.backoff_base_ms,
        backoff_jitter_ms=p.backoff_jitter_ms,
        respect_retry_after=p.respect_retry_after,
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


# ---------- pricing (#9 spend tracking) ----------


@router.get("/pricing", response_model=list[PricingTableRow])
async def get_pricing(db: AsyncSession = Depends(get_db)) -> list[PricingTableRow]:
    """Read the per-`provider:model` pricing table. Empty list if unset."""
    raw = await load_pricing(db)
    out: list[PricingTableRow] = []
    for key, rate in raw.items():
        provider, _, model = key.partition(":")
        out.append(
            PricingTableRow(
                provider_code=provider,
                model=model,
                input_per_1m=rate.get("input_per_1m"),
                output_per_1m=rate.get("output_per_1m"),
            )
        )
    return out


@router.put("/pricing", response_model=list[PricingTableRow])
async def put_pricing(
    payload: PricingTableUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> list[PricingTableRow]:
    """Idempotent overwrite — sends the full table on save. Empty/zero rates
    clear that row; a missing (provider:model) pair clears it entirely."""
    rows_dict = [r.model_dump() for r in payload.rates]
    await save_pricing(db, rows_dict, actor_id=actor.id)
    return await get_pricing(db)
