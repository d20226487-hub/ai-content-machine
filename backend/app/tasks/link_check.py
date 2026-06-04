"""Distributed, resumable link checker (fan-out + crash-resume).

Flow:
  * ``linkcheck.seed`` — flips the run to running, does the (fast, CPU-only)
    juxtapose inline, materializes one ``LinkCheckCrawlTarget`` per unique
    crawlable URL (carrying the cell occurrences it appears in), then fans
    out one ``linkcheck.crawl_chunk`` task per ``LINK_CHUNK_SIZE`` links
    across all workers. Juxtapose violations + targets + status flip commit
    in ONE transaction, so a seed crash before that commit re-runs cleanly
    (status still ``queued``) and a crash after it resumes via the chunks.
  * ``linkcheck.crawl_chunk`` — claims the ``pending`` targets for its chunk,
    crawls them in sub-batches, writes occurrence violations + flips targets
    ``done`` + bumps counters per sub-batch (one commit each). Re-querying
    ``pending`` makes it idempotent under Celery redelivery / resume.
  * finalize (advisory-locked, runs once) recomputes authoritative counters
    from the targets table and sets the run ``done``.
  * ``linkcheck.watchdog`` (beat) resumes stalled runs; ``linkcheck.resume``
    re-enqueues a run's pending chunks (also exposed as a button).

Fresh NullPool engine per task — same event-loop reason as bulk_generation.
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import (
    BulkTableCell,
    BulkTableColumn,
    BulkTableRow,
    LinkCheckCrawlTarget,
    LinkCheckRun,
    LinkCheckViolation,
)
from app.services.link_check import (
    _MAX_CRAWL_LINKS,
    CRAWL_BATCH,
    LINK_CHUNK_SIZE,
    crawl_batch,
    crawlable_url,
    extract_expected_links,
    extract_output_links,
    juxtapose,
    make_crawl_client,
    normalize_link,
)
from app.services.translation_links import (
    classify_link,
    compute_expected_links,
    parse_domains,
)
from app.tasks.celery_app import celery_app

# Namespace for the per-run finalize advisory lock (2-int form).
_ADVISORY_NS = 0x4C43  # 'LC'


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _batches(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


async def _with_session(fn: Callable[[AsyncSession], Awaitable[None]]) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with Session() as db:
            await fn(db)
    finally:
        await engine.dispose()


# ---------- Celery entrypoints ----------


@celery_app.task(name="linkcheck.seed")
def seed_link_check(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _seed(db, run_id)))
    return {"run_id": run_id, "ok": True}


@celery_app.task(name="linkcheck.crawl_chunk")
def crawl_chunk(run_id: int, chunk_index: int) -> dict:
    asyncio.run(_with_session(lambda db: _crawl_chunk(db, run_id, chunk_index)))
    return {"run_id": run_id, "chunk_index": chunk_index, "ok": True}


@celery_app.task(name="linkcheck.resume")
def resume_link_check(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _resume(db, run_id)))
    return {"run_id": run_id, "ok": True}


@celery_app.task(name="linkcheck.watchdog")
def link_check_watchdog() -> dict:
    asyncio.run(_with_session(_watchdog))
    return {"ok": True}


# ---------- seed ----------


async def _seed(db: AsyncSession, run_id: int) -> None:
    run = await db.get(LinkCheckRun, run_id)
    if run is None or run.status in ("done", "failed", "cancelled"):
        return
    if run.status == "running":
        # Redelivery after a partial seed (targets + status already
        # committed) — just make sure the crawl continues.
        await _resume(db, run_id)
        return

    # Translation mode (3rd mode): computed-expected juxtapose, no crawl. The
    # whole thing commits once, so a crash before commit re-runs cleanly.
    if run.translation_config:
        await _seed_translation(db, run)
        return

    # status == 'queued': full seed. Compute everything first, commit once.
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

    # Optional link-type classification (product / internal / external) — the
    # per-row internal domains come from the chosen column(s).
    classify = dict(run.classify_config or {})
    product_domains = classify.get("product_domains", []) or []
    domain_cols = [
        int(c)
        for c in classify.get("internal_domain_column_ids", [])
        if int(c) in valid_ids
    ]
    classify_on = bool(product_domains or domain_cols)

    target_ids = set(selected) | set(expected_cols) | set(domain_cols)
    # Optional row scope (NULL = all rows). The AI fix's auto re-check sets
    # this so only the touched rows are re-scanned.
    scope_ids = run.row_ids if isinstance(run.row_ids, list) else None
    scope_set = {int(x) for x in scope_ids} if scope_ids else None
    row_pos = {
        rid: pos
        for rid, pos in (
            await db.execute(
                select(BulkTableRow.id, BulkTableRow.position).where(
                    BulkTableRow.table_id == run.table_id
                )
            )
        ).all()
        if scope_set is None or rid in scope_set
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

    violations: list[LinkCheckViolation] = []
    omitted_n = 0
    halluc_n = 0
    # url -> [{row_id,row_position,column_id,column_name,link}, …]
    by_url: dict[str, list[dict]] = defaultdict(list)

    do_juxtapose = run.check_juxtapose and bool(expected_cols)

    for rid, pos in row_pos.items():
        colvals = by_row.get(rid, {})
        # Per-row internal domains → a classifier for this row's links.
        if classify_on:
            internal_domains: list[str] = []
            for dc in domain_cols:
                internal_domains += parse_domains(colvals.get(dc))
            lt = lambda u, _d=internal_domains: classify_link(u, _d, product_domains)
        else:
            lt = lambda u: None
        per_col: dict[int, list[str]] = {}
        union: list[str] = []
        for cid in selected:
            links = extract_output_links(colvals.get(cid))
            per_col[cid] = links
            union += links
            if run.check_crawl:
                for l in links:
                    by_url[crawlable_url(l)].append(
                        {
                            "row_id": rid,
                            "row_position": pos,
                            "column_id": cid,
                            "column_name": col_names.get(cid, "—"),
                            "link": l,
                            "link_type": lt(l),
                        }
                    )

        if do_juxtapose:
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
                        _violation(rid, pos, attr_col, col_names, "omitted", e, "expected_missing", link_type=lt(e))
                    )
                    omitted_n += 1
            for cid in selected:
                for l in per_col[cid]:
                    if normalize_link(l) not in exp_norm:
                        violations.append(
                            _violation(rid, pos, cid, col_names, "hallucinated", l, "not_in_expected", link_type=lt(l))
                        )
                        halluc_n += 1

    unique_urls = list(by_url.keys())

    # Cap guard — still save the (valuable) juxtapose result.
    if run.check_crawl and len(unique_urls) > _MAX_CRAWL_LINKS:
        for v in violations:
            v.run_id = run_id
        db.add_all(violations)
        run.omitted_count = omitted_n
        run.hallucinated_count = halluc_n
        run.status = "failed"
        run.error = (
            f"Too many links to crawl ({len(unique_urls)} > {_MAX_CRAWL_LINKS}). "
            "Narrow the selected columns and retry."
        )
        run.started_at = _now()
        run.finished_at = _now()
        await db.commit()
        return

    # ---- one atomic commit: juxtapose violations + targets + status ----
    for v in violations:
        v.run_id = run_id
    if violations:
        db.add_all(violations)
    run.omitted_count = omitted_n
    run.hallucinated_count = halluc_n
    run.status = "running"
    run.started_at = _now()
    run.last_progress_at = _now()

    crawl = run.check_crawl and bool(unique_urls)
    chunk_count = 0
    if crawl:
        run.total_links = len(unique_urls)
        target_rows = [
            {
                "run_id": run_id,
                "url": url,
                "chunk_index": i // LINK_CHUNK_SIZE,
                "state": "pending",
                "occurrences": by_url[url],
            }
            for i, url in enumerate(unique_urls)
        ]
        chunk_count = (len(unique_urls) + LINK_CHUNK_SIZE - 1) // LINK_CHUNK_SIZE
        for batch in _batches(target_rows, 1000):
            # ON CONFLICT so a re-run after a crash doesn't duplicate targets.
            await db.execute(
                pg_insert(LinkCheckCrawlTarget)
                .values(batch)
                .on_conflict_do_nothing(constraint="uq_lc_targets_run_url")
            )
    else:
        run.status = "done"
        run.finished_at = _now()

    await db.commit()

    # Fan out (after the commit so children always find their targets).
    for ci in range(chunk_count):
        crawl_chunk.delay(run_id, ci)


def _violation(
    row_id,
    pos,
    col_id,
    col_names,
    problem,
    link,
    detail_code,
    status_code=None,
    link_type=None,
) -> LinkCheckViolation:
    return LinkCheckViolation(
        row_id=row_id,
        row_position=pos,
        column_id=col_id,
        column_name=col_names.get(col_id, "—"),
        problem=problem,
        link=link,
        detail_code=detail_code,
        status_code=status_code,
        link_type=link_type,
    )


# ---------- translation-links seed ----------


async def _seed_translation(db: AsyncSession, run: LinkCheckRun) -> None:
    """Computed-expected juxtapose for the translation-links mode (no crawl).

    Per row: localize the ORIGINAL content's links (insert the row's language
    as a subfolder, per the per-type treatment), write that list into a fresh
    "Expected links" column, extract the TRANSLATION's actual links, and record
    the mismatches as violations ON the translated cell (so AI-fix rewrites the
    translation). Pointing ``expected_column_ids`` at the new column lets the
    existing AI-fix / revert / re-verify run unchanged. Everything commits once.
    """
    cfg = dict(run.translation_config or {})
    orig_col = int(cfg["original_column_id"])
    trans_col = int(cfg["translated_column_id"])
    lang_col = int(cfg["lang_column_id"])
    domain_cols = [int(c) for c in cfg.get("internal_domain_column_ids", [])]
    product_domains = cfg.get("product_domains", []) or []
    exceptions = cfg.get("exceptions", []) or []
    default_langs = cfg.get("product_default_langs", {}) or {}
    internal_t = cfg.get("internal_treatment", "skip")
    external_t = cfg.get("external_treatment", "skip")

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
    if not {orig_col, trans_col, lang_col} <= set(col_names):
        run.status = "failed"
        run.error = "A selected column was deleted before the run started."
        run.started_at = _now()
        run.finished_at = _now()
        await db.commit()
        return
    # A deleted domain column is simply dropped (not fatal).
    domain_cols = [c for c in domain_cols if c in col_names]

    # No columns are materialized (keeps the bulk table uncluttered). The
    # 4-column breakdown (original / expected / translation / mismatches) is
    # shown on the run page's raw-table view, computed on demand. Here we only
    # juxtapose to produce the run's violations.
    row_pos = dict(
        (
            await db.execute(
                select(BulkTableRow.id, BulkTableRow.position).where(
                    BulkTableRow.table_id == run.table_id
                )
            )
        ).all()
    )
    by_row: dict[int, dict[int, str | None]] = defaultdict(dict)
    cells = (
        (
            await db.execute(
                select(BulkTableCell)
                .join(BulkTableRow, BulkTableRow.id == BulkTableCell.row_id)
                .where(
                    BulkTableRow.table_id == run.table_id,
                    BulkTableCell.column_id.in_(
                        [orig_col, trans_col, lang_col, *domain_cols]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    for c in cells:
        by_row[c.row_id][c.column_id] = c.value

    violations: list[LinkCheckViolation] = []
    omitted_n = 0
    halluc_n = 0

    for rid, pos in row_pos.items():
        vals = by_row.get(rid, {})
        lang = (vals.get(lang_col) or "").strip()
        # Internal domains for this row come from the chosen domain column(s).
        internal_domains: list[str] = []
        for dc in domain_cols:
            internal_domains += parse_domains(vals.get(dc))
        expected = (
            compute_expected_links(
                vals.get(orig_col),
                lang,
                internal_domains=internal_domains,
                product_domains=product_domains,
                exceptions=exceptions,
                internal_treatment=internal_t,
                external_treatment=external_t,
                default_langs=default_langs,
            )
            if lang
            else []
        )
        # Nothing to compare against (no lang / original had no links) — skip.
        if not expected:
            continue
        actual = extract_output_links(vals.get(trans_col))
        omitted, hallucinated = juxtapose(actual, expected)
        for e in omitted:
            violations.append(
                _violation(rid, pos, trans_col, col_names, "omitted", e, "expected_missing")
            )
            omitted_n += 1
        for h in hallucinated:
            violations.append(
                _violation(rid, pos, trans_col, col_names, "hallucinated", h, "not_in_expected")
            )
            halluc_n += 1

    for v in violations:
        v.run_id = run.id
    if violations:
        db.add_all(violations)

    run.expected_column_ids = []
    run.omitted_count = omitted_n
    run.hallucinated_count = halluc_n
    run.ok_count = 0
    run.broken_count = 0
    run.status = "done"
    run.started_at = _now()
    run.finished_at = _now()
    run.last_progress_at = _now()
    await db.commit()


# ---------- crawl chunk ----------


async def _crawl_chunk(db: AsyncSession, run_id: int, chunk_index: int) -> None:
    run = await db.get(LinkCheckRun, run_id)
    if run is None or run.status in ("done", "failed", "cancelled"):
        return

    targets = (
        (
            await db.execute(
                select(LinkCheckCrawlTarget).where(
                    LinkCheckCrawlTarget.run_id == run_id,
                    LinkCheckCrawlTarget.chunk_index == chunk_index,
                    LinkCheckCrawlTarget.state == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    if not targets:
        await _finalize_if_done(db, run_id)
        return

    async with make_crawl_client() as client:
        for sub in _batches(list(targets), CRAWL_BATCH):
            await db.refresh(run)
            if run.status == "cancelled":
                return
            results = await crawl_batch(client, [t.url for t in sub])
            new_violations: list[LinkCheckViolation] = []
            ok_n = 0
            broken_n = 0
            for t in sub:
                st = results.get(t.url)
                if st is None:
                    continue
                t.state = "done"
                t.ok = st.ok
                t.status_code = st.status_code
                t.detail_code = st.detail_code
                if not st.ok:
                    broken_n += 1
                    for occ in t.occurrences:
                        new_violations.append(_occ_violation(run_id, occ, "broken", st))
                else:
                    ok_n += 1
                    if run.include_ok:
                        for occ in t.occurrences:
                            new_violations.append(_occ_violation(run_id, occ, "ok", st))
            if new_violations:
                db.add_all(new_violations)
            await db.execute(
                update(LinkCheckRun)
                .where(LinkCheckRun.id == run_id)
                .values(
                    crawled=LinkCheckRun.crawled + len(sub),
                    ok_count=LinkCheckRun.ok_count + ok_n,
                    broken_count=LinkCheckRun.broken_count + broken_n,
                    last_progress_at=_now(),
                )
            )
            await db.commit()

    await _finalize_if_done(db, run_id)


def _occ_violation(run_id: int, occ: dict, problem: str, st) -> LinkCheckViolation:
    return LinkCheckViolation(
        run_id=run_id,
        row_id=occ["row_id"],
        row_position=occ["row_position"],
        column_id=occ["column_id"],
        column_name=occ["column_name"],
        problem=problem,
        link=occ["link"],
        detail_code=st.detail_code,
        status_code=st.status_code,
        link_type=occ.get("link_type"),
    )


# ---------- finalize ----------


async def _finalize_if_done(db: AsyncSession, run_id: int) -> None:
    # Serialize finalize across the workers that may all see "0 pending".
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :rid)"),
        {"ns": _ADVISORY_NS, "rid": run_id},
    )
    run = await db.get(LinkCheckRun, run_id)
    if run is None or run.status != "running":
        await db.rollback()
        return
    pending = (
        await db.execute(
            select(func.count())
            .select_from(LinkCheckCrawlTarget)
            .where(
                LinkCheckCrawlTarget.run_id == run_id,
                LinkCheckCrawlTarget.state == "pending",
            )
        )
    ).scalar_one()
    if pending > 0:
        await db.rollback()
        return

    # Authoritative counters from the targets table (corrects any drift from
    # the incremental bumps).
    done = (
        await db.execute(
            select(func.count())
            .select_from(LinkCheckCrawlTarget)
            .where(LinkCheckCrawlTarget.run_id == run_id)
        )
    ).scalar_one()
    okc = (
        await db.execute(
            select(func.count())
            .select_from(LinkCheckCrawlTarget)
            .where(
                LinkCheckCrawlTarget.run_id == run_id,
                LinkCheckCrawlTarget.ok.is_(True),
            )
        )
    ).scalar_one()
    run.crawled = done
    run.ok_count = okc
    run.broken_count = done - okc
    run.status = "done"
    run.finished_at = _now()
    await db.commit()


# ---------- resume + watchdog ----------


async def _resume(db: AsyncSession, run_id: int) -> None:
    run = await db.get(LinkCheckRun, run_id)
    if run is None:
        return
    if run.status == "queued":
        seed_link_check.delay(run_id)
        return
    if run.status != "running":
        return
    # Debounce the watchdog so it doesn't re-pick this run next tick.
    run.last_progress_at = _now()
    await db.commit()

    chunks = (
        (
            await db.execute(
                select(LinkCheckCrawlTarget.chunk_index)
                .where(
                    LinkCheckCrawlTarget.run_id == run_id,
                    LinkCheckCrawlTarget.state == "pending",
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if not chunks:
        await _finalize_if_done(db, run_id)
        return
    for ci in chunks:
        crawl_chunk.delay(run_id, ci)


async def _watchdog(db: AsyncSession) -> None:
    """Re-enqueue runs that have stalled (worker death / lost message)."""
    rows = (
        (
            await db.execute(
                select(LinkCheckRun.id).where(
                    text(
                        "(status = 'running' AND check_crawl = true AND "
                        " (last_progress_at IS NULL OR "
                        "  last_progress_at < now() - interval '3 minutes')) "
                        "OR (status = 'queued' AND "
                        "    created_at < now() - interval '2 minutes')"
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for rid in rows:
        resume_link_check.delay(rid)
