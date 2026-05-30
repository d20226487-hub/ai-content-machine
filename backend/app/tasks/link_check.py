"""Celery task that runs a link-check over a bulk table.

One task per LinkCheckRun. It does the (fast) juxtapose pass inline, then —
if enabled — crawls the unique output links in batches, persisting progress
and honoring a Cancel between batches. All DB I/O happens here in the task's
own session (never inside a concurrent crawl worker).

Fresh NullPool engine per task for the same event-loop reason as
``bulk_generation`` — see that module's note.
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import (
    BulkTableCell,
    BulkTableColumn,
    BulkTableRow,
    LinkCheckRun,
    LinkCheckViolation,
)
from app.services.link_check import (
    _MAX_CRAWL_LINKS,
    CRAWL_BATCH,
    crawl_batch,
    crawlable_url,
    extract_expected_links,
    extract_output_links,
    make_crawl_client,
    normalize_link,
)
from app.tasks.celery_app import celery_app


def _now() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(name="linkcheck.run")
def run_link_check(run_id: int) -> dict:
    asyncio.run(_run(run_id))
    return {"run_id": run_id, "ok": True}


async def _run(run_id: int) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with Session() as db:
            await _process(db, run_id)
    except Exception as e:  # noqa: BLE001 — record + re-raise for task_failure log
        async with Session() as db:
            run = await db.get(LinkCheckRun, run_id)
            if run is not None and run.status not in ("cancelled", "done", "failed"):
                run.status = "failed"
                run.error = str(e)[:2000]
                run.finished_at = _now()
                await db.commit()
        raise
    finally:
        await engine.dispose()


def _violation(
    run_id, row_id, pos, col_id, col_names, problem, link, detail_code, status_code=None
) -> LinkCheckViolation:
    return LinkCheckViolation(
        run_id=run_id,
        row_id=row_id,
        row_position=pos,
        column_id=col_id,
        column_name=col_names.get(col_id, "—"),
        problem=problem,
        link=link,
        detail_code=detail_code,
        status_code=status_code,
    )


async def _process(db: AsyncSession, run_id: int) -> None:
    run = await db.get(LinkCheckRun, run_id)
    if run is None or run.status != "queued":
        return
    run.status = "running"
    run.started_at = _now()
    await db.commit()

    # Column metadata + the cells we need (selected output cols + expected).
    cols = (
        (
            await db.execute(
                select(BulkTableColumn).where(
                    BulkTableColumn.table_id == run.table_id
                )
            )
        )
        .scalars()
        .all()
    )
    col_names = {c.id: c.name for c in cols}
    valid_ids = set(col_names)
    selected = [cid for cid in (run.column_ids or []) if cid in valid_ids]
    expected_cols = [
        cid for cid in (run.expected_column_ids or []) if cid in valid_ids
    ]

    target_ids = set(selected) | set(expected_cols)

    row_pos = {
        rid: pos
        for rid, pos in (
            await db.execute(
                select(BulkTableRow.id, BulkTableRow.position).where(
                    BulkTableRow.table_id == run.table_id
                )
            )
        ).all()
    }

    by_row: dict[int, dict[int, str | None]] = defaultdict(dict)
    if target_ids:
        cells = (
            (
                await db.execute(
                    select(BulkTableCell)
                    .join(BulkTableRow, BulkTableRow.id == BulkTableCell.row_id)
                    .where(
                        BulkTableRow.table_id == run.table_id,
                        BulkTableCell.column_id.in_(target_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        for c in cells:
            by_row[c.row_id][c.column_id] = c.value

    # ---- juxtapose pass (instant) + collect crawl occurrences ----
    violations: list[LinkCheckViolation] = []
    omitted_n = 0
    halluc_n = 0
    # (row_id, pos, col_id, original_link)
    occurrences: list[tuple[int, int, int, str]] = []

    do_juxtapose = run.check_juxtapose and bool(expected_cols)

    for row_id, pos in row_pos.items():
        colvals = by_row.get(row_id, {})
        per_col: dict[int, list[str]] = {}
        union: list[str] = []
        for cid in selected:
            links = extract_output_links(colvals.get(cid))
            per_col[cid] = links
            union += links
            for l in links:
                occurrences.append((row_id, pos, cid, l))

        if do_juxtapose:
            # Union expected links across every expected column for this row.
            expected: list[str] = []
            for ecid in expected_cols:
                expected += extract_expected_links(colvals.get(ecid))
            exp_norm = {normalize_link(u) for u in expected}
            union_norm = {normalize_link(u) for u in union}
            attr_col = selected[0] if selected else expected_cols[0]
            seen_omit: set[str] = set()
            for e in expected:
                n = normalize_link(e)
                if n not in union_norm and n not in seen_omit:
                    seen_omit.add(n)
                    violations.append(
                        _violation(
                            run_id, row_id, pos, attr_col, col_names,
                            "omitted", e, "expected_missing",
                        )
                    )
                    omitted_n += 1
            for cid in selected:
                for l in per_col[cid]:
                    if normalize_link(l) not in exp_norm:
                        violations.append(
                            _violation(
                                run_id, row_id, pos, cid, col_names,
                                "hallucinated", l, "not_in_expected",
                            )
                        )
                        halluc_n += 1

    if violations:
        db.add_all(violations)
    run.omitted_count = omitted_n
    run.hallucinated_count = halluc_n
    await db.commit()

    # ---- crawl pass (network) ----
    if run.check_crawl and occurrences:
        unique = []
        seen: set[str] = set()
        for _r, _p, _c, link in occurrences:
            cu = crawlable_url(link)
            if cu not in seen:
                seen.add(cu)
                unique.append(cu)

        if len(unique) > _MAX_CRAWL_LINKS:
            run.status = "failed"
            run.error = (
                f"Too many links to crawl ({len(unique)} > {_MAX_CRAWL_LINKS}). "
                "Narrow the selected columns and retry."
            )
            run.finished_at = _now()
            await db.commit()
            return

        run.total_links = len(unique)
        await db.commit()

        results = {}
        crawled = 0
        async with make_crawl_client() as client:
            for i in range(0, len(unique), CRAWL_BATCH):
                await db.refresh(run)
                if run.status == "cancelled":
                    run.finished_at = _now()
                    await db.commit()
                    return
                batch = unique[i : i + CRAWL_BATCH]
                results.update(await crawl_batch(client, batch))
                crawled += len(batch)
                run.crawled = crawled
                await db.commit()

        rows_out: list[LinkCheckViolation] = []
        for row_id, pos, cid, link in occurrences:
            st = results.get(crawlable_url(link))
            if st is None:
                continue
            if st.ok:
                # Healthy link — only recorded when the operator asked for the
                # full inventory.
                if run.include_ok:
                    rows_out.append(
                        _violation(
                            run_id, row_id, pos, cid, col_names,
                            "ok", link, st.detail_code, st.status_code,
                        )
                    )
                continue
            rows_out.append(
                _violation(
                    run_id, row_id, pos, cid, col_names,
                    "broken", link, st.detail_code, st.status_code,
                )
            )
        if rows_out:
            db.add_all(rows_out)
        run.ok_count = sum(1 for s in results.values() if s.ok)
        run.broken_count = sum(1 for s in results.values() if not s.ok)
        await db.commit()

    run.status = "done"
    run.finished_at = _now()
    await db.commit()
