"""Pricing config + cost calc for usage_events.

Pricing lives in `app_settings` under the key 'pricing' as a single jsonb
blob keyed by `"provider_code:model"` (lower-cased internally). Shape:

    {
      "ai_studio:gemini-2.5-flash": {"input_per_1m": "0.075", "output_per_1m": "0.30"},
      "openrouter:openai/gpt-4o":   {"input_per_1m": "5.00",  "output_per_1m": "15.00"},
      ...
    }

Decimals are stored as JSON strings to preserve precision through
round-trips. Cost is computed at write time so historical events don't
shift when an admin updates the rate later — that's the user-visible
contract.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting
from app.services.app_settings_cache import (
    get_setting,
    invalidate as invalidate_setting,
)

PRICING_KEY = "pricing"
_TOKENS_PER_UNIT = Decimal("1000000")  # rates are per 1M tokens


def _key(provider_code: str, model: str) -> str:
    return f"{provider_code}:{model}".strip()


async def load_pricing(db: AsyncSession) -> dict[str, dict[str, Decimal | None]]:
    """Read the full pricing table (cached). Returns an empty dict if unset."""
    raw = await get_setting(db, PRICING_KEY)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Decimal | None]] = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        out[k] = {
            "input_per_1m": _to_decimal(v.get("input_per_1m")),
            "output_per_1m": _to_decimal(v.get("output_per_1m")),
        }
    return out


async def save_pricing(
    db: AsyncSession,
    rates: list[dict[str, Any]],
    *,
    actor_id: int | None,
) -> None:
    """Idempotent overwrite. Row shape: {provider_code, model, input_per_1m, output_per_1m}."""
    payload: dict[str, dict[str, str | None]] = {}
    for r in rates:
        provider = (r.get("provider_code") or "").strip()
        model = (r.get("model") or "").strip()
        if not provider or not model:
            continue
        payload[_key(provider, model)] = {
            "input_per_1m": _str_or_none(r.get("input_per_1m")),
            "output_per_1m": _str_or_none(r.get("output_per_1m")),
        }

    stmt = (
        pg_insert(AppSetting)
        .values(key=PRICING_KEY, value=payload, updated_by_id=actor_id)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": payload, "updated_by_id": actor_id},
        )
    )
    await db.execute(stmt)
    await db.commit()
    invalidate_setting(PRICING_KEY)


def compute_cost_usd(
    rates: dict[str, dict[str, Decimal | None]],
    *,
    provider_code: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> Decimal | None:
    """Best-effort cost. Returns None when no rate is configured for this
    provider:model pair, OR when the provider didn't return token counts.

    Partial pricing (only input or only output set) contributes the part we
    know — better than blanking the field entirely.
    """
    rate = rates.get(_key(provider_code, model))
    if not rate:
        return None
    inp_rate = rate.get("input_per_1m")
    out_rate = rate.get("output_per_1m")
    if inp_rate is None and out_rate is None:
        return None
    if prompt_tokens is None and completion_tokens is None:
        return None

    total = Decimal("0")
    if inp_rate is not None and prompt_tokens:
        total += (Decimal(prompt_tokens) / _TOKENS_PER_UNIT) * inp_rate
    if out_rate is not None and completion_tokens:
        total += (Decimal(completion_tokens) / _TOKENS_PER_UNIT) * out_rate
    # Quantise to 6 dp to match the column scale.
    return total.quantize(Decimal("0.000001"))


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _str_or_none(v: Any) -> str | None:
    if v is None or v == "":
        return None
    try:
        return str(Decimal(str(v)))
    except (InvalidOperation, TypeError, ValueError):
        return None
