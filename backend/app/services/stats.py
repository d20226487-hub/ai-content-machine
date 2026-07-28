"""Statistics rollup — monthly bulk-generation + publication + spend figures.

Everything is aggregated on the fly from durable per-item logs; nothing new is
stored:

  * generations → ``bulk_generation_runs`` (successful runs, done cells, failed
    cells). Failed/cancelled *runs* are excluded from the run count.
  * publications (Custom CMS) → ``publish_jobs`` filtered to ``cms_type='custom'``
    (posted vs failed). WordPress publishing goes through Autotool, so the direct
    WordPress path isn't surfaced.
  * publications (Autotool) → ``autotool_run_items`` (sent vs failed)
  * spend / tokens → ``usage_events`` (all sources)

Success counters (Generated / Custom CMS / Autotool) count ONLY successful
executions; failures are reported separately (gen_failed / pub_custom_failed /
pub_autotool_failed) for a dedicated errors view.

Filters: a specific month, a user, and/or a domain. Generations, Autotool, and
spend are NOT tied to a domain, so under a domain filter their metrics are
returned as ``None`` ("—"); only Custom CMS publications are domain-scoped.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Integer, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AutotoolRun,
    AutotoolRunItem,
    BulkGenerationRun,
    BulkTable,
    Domain,
    PublishJob,
    UsageEvent,
    User,
)
from app.schemas.stats import (
    BreakdownRow,
    MonthStat,
    StatFilterOption,
    StatMetrics,
    StatsFilters,
    StatsResponse,
)

_MONTH_FMT = "YYYY-MM"
_MONTH_CHOICES = 24  # months offered in the month-filter dropdown
_MAX_BREAKDOWN_ROWS = 100
# Runs in these states didn't produce a completed batch → excluded from counts.
_DEAD_RUN_STATES = ("failed", "cancelled")


# ---------- time window ----------


def _add_months(dt: datetime, n: int) -> datetime:
    idx = dt.year * 12 + (dt.month - 1) + n
    return datetime(idx // 12, idx % 12 + 1, 1, tzinfo=timezone.utc)


def _window(month: str | None, months: int) -> tuple[datetime, datetime | None]:
    """(start, end) for the query. ``end`` is None for the open-ended lookback."""
    now = datetime.now(timezone.utc)
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month:
        try:
            start = datetime(int(month[:4]), int(month[5:7]), 1, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            return _add_months(first, -(max(1, months) - 1)), None
        return start, _add_months(start, 1)
    return _add_months(first, -(max(1, months) - 1)), None


def _mkey(col):
    return func.to_char(func.date_trunc("month", col), _MONTH_FMT)


def _bounded(q, col, start, end):
    q = q.where(col >= start)
    if end is not None:
        q = q.where(col < end)
    return q


def _posted_cond(only_content: bool):
    """Successful-publish predicate. With ``only_content`` also require a
    non-empty ``content`` field in the sent payload (Custom CMS). Autotool
    always ships the content column, so its own query isn't gated."""
    cond = PublishJob.status == "posted"
    if only_content:
        cond = and_(
            cond,
            func.coalesce(PublishJob.payload_sent["content"].astext, "") != "",
        )
    return cond


# ---------- per-month overview ----------


async def _overview(
    db: AsyncSession, start, end, user_id: int | None, domain_id: int | None,
    only_content: bool = False,
) -> tuple[list[MonthStat], StatMetrics]:
    dom = domain_id is not None
    gen: dict[str, tuple] = {}
    pub: dict[str, list] = {}   # [custom_posted, custom_failed]
    auto: dict[str, tuple] = {}  # (sent, failed)
    spend: dict[str, tuple] = {}

    if not dom:
        me = _mkey(BulkGenerationRun.created_at)
        q = _bounded(
            select(
                me.label("m"),
                func.count().label("runs"),
                func.coalesce(func.sum(BulkGenerationRun.done), 0).label("cells"),
                func.coalesce(func.sum(BulkGenerationRun.failed), 0).label("failed"),
            ).where(BulkGenerationRun.status.notin_(_DEAD_RUN_STATES)),
            BulkGenerationRun.created_at, start, end,
        )
        if user_id is not None:
            q = q.where(BulkGenerationRun.created_by_id == user_id)
        for m, runs, cells, failed in (await db.execute(q.group_by(me))).all():
            gen[m] = (int(runs), int(cells), int(failed))

    me = _mkey(PublishJob.created_at)
    q = _bounded(
        select(
            me.label("m"),
            Domain.cms_type.label("cms"),
            func.count().filter(_posted_cond(only_content)).label("posted"),
            func.count().filter(PublishJob.status == "failed").label("failed"),
        ).select_from(PublishJob).join(
            Domain, Domain.id == PublishJob.domain_id, isouter=True
        ),
        PublishJob.created_at, start, end,
    )
    if user_id is not None:
        q = q.where(PublishJob.created_by_id == user_id)
    if domain_id is not None:
        q = q.where(PublishJob.domain_id == domain_id)
    for m, cms, posted, failed in (await db.execute(q.group_by(me, Domain.cms_type))).all():
        row = pub.setdefault(m, [0, 0])
        if cms == "custom":
            row[0] += int(posted)
            row[1] += int(failed)

    if not dom:
        me = _mkey(AutotoolRunItem.created_at)
        q = _bounded(
            select(
                me.label("m"),
                func.count().filter(AutotoolRunItem.status == "sent").label("sent"),
                func.count().filter(AutotoolRunItem.status == "failed").label("failed"),
            ).select_from(AutotoolRunItem).join(
                AutotoolRun, AutotoolRun.id == AutotoolRunItem.run_id
            ),
            AutotoolRunItem.created_at, start, end,
        )
        if user_id is not None:
            q = q.where(AutotoolRun.created_by_id == user_id)
        for m, sent, failed in (await db.execute(q.group_by(me))).all():
            auto[m] = (int(sent), int(failed))

    if not dom:
        me = _mkey(UsageEvent.created_at)
        q = _bounded(
            select(
                me.label("m"),
                func.coalesce(func.sum(UsageEvent.cost_usd), 0).label("cost"),
                func.coalesce(
                    func.sum(
                        func.coalesce(UsageEvent.prompt_tokens, 0)
                        + func.coalesce(UsageEvent.completion_tokens, 0)
                    ),
                    0,
                ).label("tok"),
            ),
            UsageEvent.created_at, start, end,
        )
        if user_id is not None:
            q = q.where(UsageEvent.user_id == user_id)
        for m, cost, tok in (await db.execute(q.group_by(me))).all():
            spend[m] = (float(cost), int(tok))

    keys = sorted(set(gen) | set(pub) | set(auto) | set(spend), reverse=True)
    rows: list[MonthStat] = []
    for m in keys:
        g = gen.get(m)
        p = pub.get(m, [0, 0])
        a = auto.get(m)
        s = spend.get(m)
        rows.append(
            MonthStat(
                month=m,
                gen_runs=None if dom else (g[0] if g else 0),
                gen_cells=None if dom else (g[1] if g else 0),
                gen_failed=None if dom else (g[2] if g else 0),
                pub_custom=p[0],
                pub_custom_failed=p[1],
                pub_autotool=None if dom else (a[0] if a else 0),
                pub_autotool_failed=None if dom else (a[1] if a else 0),
                cost_usd=None if dom else (s[0] if s else 0.0),
                tokens=None if dom else (s[1] if s else 0),
            )
        )
    return rows, _sum_metrics(rows, dom)


def _sum_metrics(rows: list[MonthStat], dom: bool) -> StatMetrics:
    def s(attr: str) -> int:
        return sum(int(getattr(r, attr) or 0) for r in rows)

    return StatMetrics(
        gen_runs=None if dom else s("gen_runs"),
        gen_cells=None if dom else s("gen_cells"),
        gen_failed=None if dom else s("gen_failed"),
        pub_custom=s("pub_custom"),
        pub_custom_failed=s("pub_custom_failed"),
        pub_autotool=None if dom else s("pub_autotool"),
        pub_autotool_failed=None if dom else s("pub_autotool_failed"),
        cost_usd=None if dom else round(sum(float(r.cost_usd or 0.0) for r in rows), 4),
        tokens=None if dom else s("tokens"),
    )


# ---------- breakdown (success + error metrics, grouped by one dimension) ----------

# Slot order: 0 gen_runs 1 gen_cells 2 gen_failed 3 custom 4 custom_failed
#             5 autotool 6 autotool_failed 7 cost 8 tokens
def _blank() -> list:
    return [0, 0, 0, 0, 0, 0, 0, 0.0, 0]


def _score(v: list) -> float:
    return v[1] + v[3] + v[5] + v[7]  # success activity: cells + custom + autotool + cost


def _rows(acc: dict, dom: bool, labeler, prefix: str, *, gen=True, spend=True,
          pub_custom=True, autotool=True) -> list[BreakdownRow]:
    out: list[BreakdownRow] = []
    for k, v in sorted(acc.items(), key=lambda kv: _score(kv[1]), reverse=True)[
        :_MAX_BREAKDOWN_ROWS
    ]:
        sg = gen and not dom
        ss = spend and not dom
        sa = autotool and not dom
        out.append(
            BreakdownRow(
                key=f"{prefix}:{'none' if k is None else k}",
                label=labeler(k),
                gen_runs=v[0] if sg else None,
                gen_cells=v[1] if sg else None,
                gen_failed=v[2] if sg else None,
                pub_custom=v[3] if pub_custom else None,
                pub_custom_failed=v[4] if pub_custom else None,
                pub_autotool=v[5] if sa else None,
                pub_autotool_failed=v[6] if sa else None,
                cost_usd=round(v[7], 4) if ss else None,
                tokens=v[8] if ss else None,
            )
        )
    return out


async def _gen_group(db, col, start, end, user_id):
    q = _bounded(
        select(
            col.label("k"),
            func.count(),
            func.coalesce(func.sum(BulkGenerationRun.done), 0),
            func.coalesce(func.sum(BulkGenerationRun.failed), 0),
        ).where(BulkGenerationRun.status.notin_(_DEAD_RUN_STATES)),
        BulkGenerationRun.created_at, start, end,
    )
    if user_id is not None:
        q = q.where(BulkGenerationRun.created_by_id == user_id)
    return (await db.execute(q.group_by(col))).all()


async def _pub_group(db, col, start, end, user_id, domain_id, only_content=False):
    q = _bounded(
        select(
            col.label("k"),
            Domain.cms_type,
            func.count().filter(_posted_cond(only_content)),
            func.count().filter(PublishJob.status == "failed"),
        ).select_from(PublishJob).join(
            Domain, Domain.id == PublishJob.domain_id, isouter=True
        ),
        PublishJob.created_at, start, end,
    )
    if user_id is not None:
        q = q.where(PublishJob.created_by_id == user_id)
    if domain_id is not None:
        q = q.where(PublishJob.domain_id == domain_id)
    return (await db.execute(q.group_by(col, Domain.cms_type))).all()


async def _auto_group(db, col, start, end, user_id):
    q = _bounded(
        select(
            col.label("k"),
            func.count().filter(AutotoolRunItem.status == "sent"),
            func.count().filter(AutotoolRunItem.status == "failed"),
        ).select_from(AutotoolRunItem).join(
            AutotoolRun, AutotoolRun.id == AutotoolRunItem.run_id
        ),
        AutotoolRunItem.created_at, start, end,
    )
    if user_id is not None:
        q = q.where(AutotoolRun.created_by_id == user_id)
    return (await db.execute(q.group_by(col))).all()


async def _spend_group(db, col, start, end, user_id):
    q = _bounded(
        select(
            col.label("k"),
            func.coalesce(func.sum(UsageEvent.cost_usd), 0),
            func.coalesce(
                func.sum(
                    func.coalesce(UsageEvent.prompt_tokens, 0)
                    + func.coalesce(UsageEvent.completion_tokens, 0)
                ),
                0,
            ),
        ),
        UsageEvent.created_at, start, end,
    )
    if user_id is not None:
        q = q.where(UsageEvent.user_id == user_id)
    return (await db.execute(q.group_by(col))).all()


async def _breakdown(
    db: AsyncSession, start, end, user_id, domain_id, group_by: str,
    only_content: bool = False,
) -> list[BreakdownRow]:
    dom = domain_id is not None
    acc: dict = {}

    def b(k):
        return acc.setdefault(k, _blank())

    if group_by == "user":
        if not dom:
            for k, runs, cells, failed in await _gen_group(
                db, BulkGenerationRun.created_by_id, start, end, user_id
            ):
                r = b(k); r[0] += int(runs); r[1] += int(cells); r[2] += int(failed)
        for k, cms, posted, failed in await _pub_group(
            db, PublishJob.created_by_id, start, end, user_id, domain_id, only_content
        ):
            if cms == "custom":
                r = b(k); r[3] += int(posted); r[4] += int(failed)
        if not dom:
            for k, sent, failed in await _auto_group(
                db, AutotoolRun.created_by_id, start, end, user_id
            ):
                r = b(k); r[5] += int(sent); r[6] += int(failed)
            for k, cost, tok in await _spend_group(
                db, UsageEvent.user_id, start, end, user_id
            ):
                r = b(k); r[7] += float(cost); r[8] += int(tok)
        names = await _user_labels(db, [k for k in acc if k is not None])
        return _rows(acc, dom, lambda k: names.get(k, "—") if k else "—", "u")

    if group_by == "table":
        if not dom:
            for k, runs, cells, failed in await _gen_group(
                db, BulkGenerationRun.table_id, start, end, user_id
            ):
                r = b(k); r[0] += int(runs); r[1] += int(cells); r[2] += int(failed)
            for k, sent, failed in await _auto_group(
                db, AutotoolRun.table_id, start, end, user_id
            ):
                r = b(k); r[5] += int(sent); r[6] += int(failed)
            tcol = UsageEvent.source_ref["table_id"].astext.cast(Integer)
            for k, cost, tok in await _spend_group(db, tcol, start, end, user_id):
                r = b(k); r[7] += float(cost); r[8] += int(tok)
        names = await _table_labels(db, [k for k in acc if k is not None])
        # Custom CMS publications have no table link → shown as "—".
        return _rows(acc, dom, lambda k: names.get(k, "—") if k else "—", "t",
                     pub_custom=False)

    if group_by == "domain":
        for k, cms, posted, failed in await _pub_group(
            db, PublishJob.domain_id, start, end, user_id, domain_id, only_content
        ):
            if cms == "custom":
                r = b(k); r[3] += int(posted); r[4] += int(failed)
        names = await _domain_labels(db, [k for k in acc if k is not None])
        # Only Custom CMS publications are domain-scoped.
        return _rows(acc, dom, lambda k: names.get(k, "—") if k else "—", "d",
                     gen=False, spend=False, autotool=False)

    # channel: Custom CMS + Autotool
    _months, totals = await _overview(db, start, end, user_id, domain_id, only_content)
    out = [
        BreakdownRow(key="ch:custom", label="Custom CMS",
                     gen_runs=None, gen_cells=None, gen_failed=None,
                     pub_custom=totals.pub_custom,
                     pub_custom_failed=totals.pub_custom_failed,
                     pub_autotool=0, pub_autotool_failed=None,
                     cost_usd=None, tokens=None),
    ]
    if not dom:
        out.append(
            BreakdownRow(key="ch:autotool", label="Autotool",
                         gen_runs=None, gen_cells=None, gen_failed=None,
                         pub_custom=0, pub_custom_failed=None,
                         pub_autotool=totals.pub_autotool,
                         pub_autotool_failed=totals.pub_autotool_failed,
                         cost_usd=None, tokens=None)
        )
    return out


async def _user_labels(db, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.full_name, User.email).where(User.id.in_(ids))
        )
    ).all()
    return {uid: (full or email) for uid, full, email in rows}


async def _table_labels(db, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(BulkTable.id, BulkTable.name).where(BulkTable.id.in_(ids))
        )
    ).all()
    return {tid: name for tid, name in rows}


async def _domain_labels(db, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(Domain.id, Domain.name).where(Domain.id.in_(ids))
        )
    ).all()
    return {did: name for did, name in rows}


# ---------- filter options ----------


async def _filters(db: AsyncSession) -> StatsFilters:
    users = [
        StatFilterOption(id=uid, name=(full or email))
        for uid, full, email in (
            await db.execute(
                select(User.id, User.full_name, User.email).order_by(User.email)
            )
        ).all()
    ]
    domains = [
        StatFilterOption(id=did, name=name)
        for did, name in (
            await db.execute(select(Domain.id, Domain.name).order_by(Domain.name))
        ).all()
    ]
    # Only months that actually have data (any of the four sources) — no
    # pre-launch/empty months, newest first, deduped.
    month_set: set[str] = set()
    for col in (
        BulkGenerationRun.created_at,
        PublishJob.created_at,
        AutotoolRunItem.created_at,
        UsageEvent.created_at,
    ):
        rows = (
            await db.execute(select(_mkey(col)).distinct())
        ).all()
        month_set.update(m for (m,) in rows if m)
    months = sorted(month_set, reverse=True)[:_MONTH_CHOICES]
    return StatsFilters(users=users, domains=domains, months=months)


# ---------- public entrypoint ----------


async def get_stats(
    db: AsyncSession,
    *,
    month: str | None,
    months: int,
    user_id: int | None,
    domain_id: int | None,
    group_by: str,
    only_content: bool = False,
) -> StatsResponse:
    if group_by not in ("user", "table", "domain", "channel"):
        group_by = "user"
    start, end = _window(month, months)
    month_rows, totals = await _overview(db, start, end, user_id, domain_id, only_content)
    breakdown = await _breakdown(
        db, start, end, user_id, domain_id, group_by, only_content
    )
    filters = await _filters(db)
    return StatsResponse(
        months=month_rows,
        totals=totals,
        breakdown=breakdown,
        group_by=group_by,
        domain_scoped=domain_id is not None,
        filters=filters,
    )
