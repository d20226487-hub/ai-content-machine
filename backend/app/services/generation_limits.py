"""Resolve effective output-token limits for a generation call.

Order of precedence (first non-None wins):
  1. column.max_output_tokens                        — per-column override
  2. app_settings['generation_default_max_output_tokens'] — global default
  3. hardcoded fallback (matches the migration seed)

Why this exists: bulk generation used to pass a hardcoded
``max_output_tokens=2048`` for every cell, which truncated long-form output at
roughly 5.7k characters — and did so *invisibly*, because the truncation signal
was never read (see ``is_truncated``).

The thinking budget is deliberately global-only and unset by default. Models
that bill reasoning against the output budget (Gemini 2.5, Claude Sonnet 5)
will otherwise spend part of the ceiling thinking, leaving a variable amount
for the actual answer — the reason truncation length differed row to row. We
don't send the field at all unless an operator sets it, so models whose
thinking API differs (e.g. Gemini 3.x) can't be handed a field they'd reject.

Mirrors the shape of services/publish_rate_limit.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting
from app.providers.base import is_truncated  # re-exported for callers here
from app.services.app_settings_cache import (
    get_settings_many,
    invalidate as invalidate_setting,
)

__all__ = [
    "GenerationLimits",
    "HARDCODED_MAX_OUTPUT_TOKENS",
    "KEY_MAX_OUTPUT_TOKENS",
    "KEY_THINKING_BUDGET",
    "is_truncated",
    "load_generation_limits",
    "resolve_max_output_tokens",
    "update_generation_limits",
]

# 4x the old hardcoded 2048. Enough for a long article plus reasoning overhead
# on models that share the budget.
HARDCODED_MAX_OUTPUT_TOKENS = 8192

KEY_MAX_OUTPUT_TOKENS = "generation_default_max_output_tokens"
KEY_THINKING_BUDGET = "generation_thinking_budget"


@dataclass
class GenerationLimits:
    max_output_tokens: int
    thinking_budget: int | None


async def load_generation_limits(db: AsyncSession) -> GenerationLimits:
    """Global defaults. Cached read — bulk runs land here once per cell."""
    by_key = await get_settings_many(
        db, [KEY_MAX_OUTPUT_TOKENS, KEY_THINKING_BUDGET]
    )

    raw_max = by_key.get(KEY_MAX_OUTPUT_TOKENS)
    try:
        max_tokens = (
            int(raw_max) if raw_max is not None else HARDCODED_MAX_OUTPUT_TOKENS
        )
    except (TypeError, ValueError):
        max_tokens = HARDCODED_MAX_OUTPUT_TOKENS
    if max_tokens < 1:
        max_tokens = HARDCODED_MAX_OUTPUT_TOKENS

    raw_think = by_key.get(KEY_THINKING_BUDGET)
    try:
        # null/absent -> None, meaning "send nothing, use the model default".
        thinking = int(raw_think) if raw_think is not None else None
    except (TypeError, ValueError):
        thinking = None
    if thinking is not None and thinking < 0:
        thinking = None

    return GenerationLimits(
        max_output_tokens=max_tokens, thinking_budget=thinking
    )


def resolve_max_output_tokens(
    column_override: int | None, limits: GenerationLimits
) -> int:
    """Per-column override wins; otherwise the global default."""
    if column_override is not None and column_override > 0:
        return column_override
    return limits.max_output_tokens


async def update_generation_limits(
    db: AsyncSession, values: GenerationLimits, updated_by_id: int | None
) -> GenerationLimits:
    """Persist the global defaults. Mirrors publish_rate_limit's updater."""
    for key, v in (
        (KEY_MAX_OUTPUT_TOKENS, values.max_output_tokens),
        (KEY_THINKING_BUDGET, values.thinking_budget),
    ):
        existing = await db.get(AppSetting, key)
        if existing is None:
            existing = AppSetting(key=key, value=v)
            db.add(existing)
        else:
            existing.value = v
        existing.updated_by_id = updated_by_id
        # Drop the cached value so this worker sees the new one immediately.
        # Cross-worker propagation happens on the cache TTL boundary.
        invalidate_setting(key)
    await db.commit()
    return values
