"""Schemas for the spend-tracking surface (read-only API + pricing config)."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PricingRate(BaseModel):
    """Per-model pricing in USD per million tokens.

    Both fields nullable so an admin can configure input cost without
    knowing output cost yet. Cost calc is best-effort: if either rate is
    missing for a model, the corresponding token bucket contributes 0,
    and a fully-missing model produces NULL cost_usd in usage_events.
    """

    input_per_1m: Decimal | None = Field(default=None, ge=0)
    output_per_1m: Decimal | None = Field(default=None, ge=0)


class PricingTableRow(BaseModel):
    """One row in the admin Pricing UI: keys + the rate values."""

    provider_code: str
    model: str
    input_per_1m: Decimal | None = None
    output_per_1m: Decimal | None = None


class PricingTableUpdate(BaseModel):
    """The Pricing card sends the full table on save (idempotent overwrite)."""

    rates: list[PricingTableRow] = Field(default_factory=list)


class SpendWindow(BaseModel):
    """USD aggregates for one user across the standard time windows.

    `today` covers events created since 00:00 UTC.
    `this_week` is rolling 7 days back from now.
    `this_month` covers events created since the 1st of the current UTC month.
    `all_time` is the lifetime aggregate.

    `events` is the matching event count for each window.
    """

    model_config = ConfigDict(from_attributes=True)

    today_usd: Decimal = Decimal("0")
    today_events: int = 0
    this_week_usd: Decimal = Decimal("0")
    this_week_events: int = 0
    this_month_usd: Decimal = Decimal("0")
    this_month_events: int = 0
    all_time_usd: Decimal = Decimal("0")
    all_time_events: int = 0


class UserSpendSummary(BaseModel):
    """Per-user spend row for the /users table."""

    user_id: int | None  # None when the original user was deleted
    user_email: str | None
    user_name: str | None
    spend: SpendWindow
