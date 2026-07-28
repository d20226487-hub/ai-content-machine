"""Schemas for the Statistics page (monthly bulk-generation + publication rollup).

All figures are aggregated on the fly from durable per-item logs
(``bulk_generation_runs``, ``publish_jobs`` + ``domains``, ``autotool_run_items``,
``usage_events``) — see ``services/stats.py``. Nothing new is stored.

A ``None`` metric means "not applicable to this view" (e.g. generations/spend
under a domain filter — they aren't tied to a domain) and renders as "—".
A ``0`` means "applicable, but nothing happened".
"""
from pydantic import BaseModel


class StatMetrics(BaseModel):
    gen_runs: int | None = 0            # successful bulk-generation runs (excl. failed/cancelled)
    gen_cells: int | None = 0           # cells generated (successful)
    gen_failed: int | None = 0          # generation cells that failed
    pub_custom: int | None = 0          # posts published to Custom CMS (successful)
    pub_custom_failed: int | None = 0   # Custom CMS publish attempts that failed
    pub_autotool: int | None = 0        # items delivered via Autotool (successful)
    pub_autotool_failed: int | None = 0 # Autotool deliveries that failed
    cost_usd: float | None = 0.0        # AI spend (all sources)
    tokens: int | None = 0              # prompt + completion tokens (all sources)


class MonthStat(StatMetrics):
    month: str  # "YYYY-MM"


class BreakdownRow(StatMetrics):
    key: str    # stable identity for the row (id or literal)
    label: str  # display name


class StatFilterOption(BaseModel):
    id: int
    name: str


class StatsFilters(BaseModel):
    users: list[StatFilterOption] = []
    domains: list[StatFilterOption] = []
    months: list[str] = []  # selectable "YYYY-MM" values, newest first


class StatsResponse(BaseModel):
    months: list[MonthStat] = []
    totals: StatMetrics
    breakdown: list[BreakdownRow] = []
    group_by: str  # 'user' | 'table' | 'domain' | 'channel'
    # True when a domain filter is active — generations/spend are then N/A.
    domain_scoped: bool = False
    filters: StatsFilters
