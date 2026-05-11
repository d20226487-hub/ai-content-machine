"""Record + aggregate per-call LLM spend.

`record_usage(...)` is called from each generation site (single, bulk_cell,
ai_assist) right after a successful LLM response. It computes USD cost
from the current pricing table and inserts one row in usage_events.

The recorder is intentionally fail-soft: an exception while writing the
usage row never propagates to break the user's actual generation. We log
and move on. Spend tracking is a track-only feature; losing one event
beats failing the user's request.

Aggregation queries for the /users page live in `summary_for_user` /
`summary_for_all`. They use Postgres date arithmetic so the windows are
consistent with the operator's timezone — currently all timestamps are
stored UTC, so windows are UTC-anchored too.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageEvent, User
from app.services.pricing import compute_cost_usd, load_pricing

log = logging.getLogger("acm.usage")


async def record_usage(
    db: AsyncSession,
    *,
    user_id: int | None,
    provider_code: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    source: str,  # 'single' | 'bulk_cell' | 'ai_assist'
    source_ref: dict[str, Any] | None = None,
) -> None:
    """Best-effort: insert one usage_events row, swallow any error."""
    try:
        rates = await load_pricing(db)
        cost = compute_cost_usd(
            rates,
            provider_code=provider_code,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        ev = UsageEvent(
            user_id=user_id,
            provider_code=provider_code,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            source=source,
            source_ref=source_ref,
        )
        db.add(ev)
        await db.commit()
    except Exception:
        log.exception("usage recording failed (non-fatal)", extra={
            "user_id": user_id,
            "provider_code": provider_code,
            "model": model,
            "source": source,
        })


# --- aggregation ---------------------------------------------------------


def _windows() -> dict[str, datetime]:
    """The four time-window cutoffs (UTC). Anything created at-or-after
    each cutoff counts toward that window."""
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)  # rolling 7-day window
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {"today": today, "this_week": week, "this_month": month}


async def summary_for_user(
    db: AsyncSession, user_id: int
) -> dict[str, Any]:
    """Return per-window {usd, events} for a single user."""
    cutoffs = _windows()

    # One round-trip — SUM-FILTER pattern over the four windows.
    stmt = select(
        func.coalesce(
            func.sum(UsageEvent.cost_usd).filter(UsageEvent.created_at >= cutoffs["today"]),
            0,
        ).label("today_usd"),
        func.count(UsageEvent.id).filter(UsageEvent.created_at >= cutoffs["today"]).label("today_events"),
        func.coalesce(
            func.sum(UsageEvent.cost_usd).filter(UsageEvent.created_at >= cutoffs["this_week"]),
            0,
        ).label("this_week_usd"),
        func.count(UsageEvent.id).filter(UsageEvent.created_at >= cutoffs["this_week"]).label("this_week_events"),
        func.coalesce(
            func.sum(UsageEvent.cost_usd).filter(UsageEvent.created_at >= cutoffs["this_month"]),
            0,
        ).label("this_month_usd"),
        func.count(UsageEvent.id).filter(UsageEvent.created_at >= cutoffs["this_month"]).label("this_month_events"),
        func.coalesce(func.sum(UsageEvent.cost_usd), 0).label("all_time_usd"),
        func.count(UsageEvent.id).label("all_time_events"),
    ).where(UsageEvent.user_id == user_id)

    row = (await db.execute(stmt)).one()
    return {
        "today_usd": _to_decimal(row.today_usd),
        "today_events": int(row.today_events or 0),
        "this_week_usd": _to_decimal(row.this_week_usd),
        "this_week_events": int(row.this_week_events or 0),
        "this_month_usd": _to_decimal(row.this_month_usd),
        "this_month_events": int(row.this_month_events or 0),
        "all_time_usd": _to_decimal(row.all_time_usd),
        "all_time_events": int(row.all_time_events or 0),
    }


async def summary_for_all_users(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Per-user spend rows for every user in the system, plus one entry for
    orphaned events (user_id IS NULL after a user was deleted).

    Returns rows in the same order as the users list (by id), with deleted
    bucket appended if present. Designed for the /users page table.
    """
    cutoffs = _windows()
    stmt = (
        select(
            UsageEvent.user_id,
            func.coalesce(
                func.sum(UsageEvent.cost_usd).filter(UsageEvent.created_at >= cutoffs["today"]),
                0,
            ).label("today_usd"),
            func.count(UsageEvent.id).filter(UsageEvent.created_at >= cutoffs["today"]).label("today_events"),
            func.coalesce(
                func.sum(UsageEvent.cost_usd).filter(UsageEvent.created_at >= cutoffs["this_week"]),
                0,
            ).label("this_week_usd"),
            func.count(UsageEvent.id).filter(UsageEvent.created_at >= cutoffs["this_week"]).label("this_week_events"),
            func.coalesce(
                func.sum(UsageEvent.cost_usd).filter(UsageEvent.created_at >= cutoffs["this_month"]),
                0,
            ).label("this_month_usd"),
            func.count(UsageEvent.id).filter(UsageEvent.created_at >= cutoffs["this_month"]).label("this_month_events"),
            func.coalesce(func.sum(UsageEvent.cost_usd), 0).label("all_time_usd"),
            func.count(UsageEvent.id).label("all_time_events"),
        )
        .group_by(UsageEvent.user_id)
    )
    rows = (await db.execute(stmt)).all()
    by_user: dict[int | None, dict[str, Any]] = {}
    for r in rows:
        by_user[r.user_id] = {
            "today_usd": _to_decimal(r.today_usd),
            "today_events": int(r.today_events or 0),
            "this_week_usd": _to_decimal(r.this_week_usd),
            "this_week_events": int(r.this_week_events or 0),
            "this_month_usd": _to_decimal(r.this_month_usd),
            "this_month_events": int(r.this_month_events or 0),
            "all_time_usd": _to_decimal(r.all_time_usd),
            "all_time_events": int(r.all_time_events or 0),
        }

    # Pull users so we can attach name/email even when they have no spend.
    user_rows = (
        await db.execute(select(User).order_by(User.id))
    ).scalars().all()

    out: list[dict[str, Any]] = []
    for u in user_rows:
        spend = by_user.pop(u.id, _empty_window())
        out.append(
            {
                "user_id": u.id,
                "user_email": u.email,
                "user_name": u.full_name,
                "spend": spend,
            }
        )
    # Append the orphaned bucket if there's any history with a deleted user.
    if None in by_user:
        out.append(
            {
                "user_id": None,
                "user_email": None,
                "user_name": None,
                "spend": by_user[None],
            }
        )
    return out


def _empty_window() -> dict[str, Any]:
    return {
        "today_usd": Decimal("0"),
        "today_events": 0,
        "this_week_usd": Decimal("0"),
        "this_week_events": 0,
        "this_month_usd": Decimal("0"),
        "this_month_events": 0,
        "all_time_usd": Decimal("0"),
        "all_time_events": 0,
    }


def _to_decimal(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return Decimal("0")
