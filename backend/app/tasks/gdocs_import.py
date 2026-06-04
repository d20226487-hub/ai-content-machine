"""Background worker for the Google-Docs → Custom-CMS importer.

The API endpoint stores the uploaded JSON on a ``GdocsImportRun`` (``queued``)
and enqueues ``gdocs_import.run``. This task:

  1. Resolves an AI provider/model once.
  2. For every linked Doc: cleans the exported HTML (deterministic) and pulls
     its meta title/description (deterministic, AI fallback), stripping the
     meta block from the body. Bounded concurrency; progress per chunk.
  3. For every sheet row: pairs each Structure page to a Doc (exact match, AI
     for the remainder), then emits one table row per page with the Custom-CMS
     fields (domain[multi]/language/slug/title/content/seo_title/
     seo_description/post_id/post_url).
  4. Builds the bulk table (single- or multi-site by distinct domain count).

Cancel is observed between chunks. Fresh NullPool engine per task (event-loop
isolation, same as the other task modules).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import (
    BulkTable,
    BulkTableCell,
    BulkTableColumn,
    BulkTableRow,
    GdocsImportRun,
)
from app.providers.base import BaseProvider
from app.providers.registry import get_provider
from app.services.ai_assist import first_enabled_provider_code
from app.services.brain import gdocs_meta_prompt, gdocs_pairing_prompt
from app.services.gdocs_ai import DocToPair, extract_meta, pair_docs_to_structure
from app.services.gdocs_build import (
    NO_EXACT_SLUG,
    column_layout,
    decide_mode,
    is_page_entry,
    slug_from_link,
)
from app.services.gdocs_clean import clean_doc_html
from app.tasks.celery_app import celery_app

# Docs / rows processed per concurrency wave before a progress commit + cancel
# check. Small enough that Cancel is observed promptly.
DOC_CHUNK = 20
ROW_CHUNK = 25
DOC_CONCURRENCY = 5
ROW_CONCURRENCY = 5
MAX_WARNINGS = 500

# A run with no progress for this long is considered dead (worker restart /
# crash / lost broker message) and flipped to 'failed' by the watchdog. Set
# generously: progress commits land per chunk, and a slow chunk (many AI
# calls) can take minutes — this threshold is well above any legitimate gap.
STUCK_MINUTES = 10

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


@celery_app.task(name="gdocs_import.run")
def run_gdocs_import(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _run(db, run_id)))
    return {"run_id": run_id, "ok": True}


async def _is_cancelled(db: AsyncSession, run_id: int) -> bool:
    fresh = await db.get(GdocsImportRun, run_id)
    return fresh is None or fresh.status == "cancelled"


def _clear_payload(run: GdocsImportRun) -> None:
    """Drop the bulky uploaded JSON once a run is terminal.

    The payload (sheet rows + every linked Doc's HTML, up to tens of MB) is
    only needed while the job runs. Nulling it on completion keeps the row —
    and every DB backup — small. Counters / warnings / error stay for the
    history view."""
    run.payload = {}


async def _fail(db: AsyncSession, run: GdocsImportRun, message: str) -> None:
    run.status = "failed"
    run.error = message
    run.finished_at = _now()
    _clear_payload(run)
    await db.commit()


async def _run(db: AsyncSession, run_id: int) -> None:
    """Claim the run, then execute under a crash guard.

    An unhandled exception in ``_execute`` (a slow AI call throwing, a bad
    Doc payload, etc.) would otherwise leave the run stuck on 'running'
    forever — the progress page would poll it indefinitely. The guard rolls
    back any half-built table and flips the run to 'failed' with the error.
    The ``gdocs_import.watchdog`` beat task is the backstop for the case the
    worker dies outright (no exception to catch)."""
    run = await db.get(GdocsImportRun, run_id)
    if run is None or run.status in ("done", "failed"):
        return
    if run.status == "cancelled":
        if run.finished_at is None:
            run.finished_at = _now()
            _clear_payload(run)
            await db.commit()
        return

    run.status = "running"
    run.started_at = run.started_at or _now()
    run.last_progress_at = _now()
    await db.commit()

    try:
        await _execute(db, run_id)
    except Exception as exc:
        # The work may hold uncommitted objects (e.g. a partially-built
        # table). Roll those back so we never persist a half-table, then
        # record the failure on a clean session.
        await db.rollback()
        logger.exception("gdocs_import run %s crashed", run_id)
        fresh = await db.get(GdocsImportRun, run_id)
        if fresh is not None and fresh.status not in ("done", "cancelled"):
            fresh.status = "failed"
            fresh.error = f"Import crashed: {type(exc).__name__}: {exc}"[:2000]
            fresh.finished_at = _now()
            _clear_payload(fresh)
            await db.commit()


async def _execute(db: AsyncSession, run_id: int) -> None:
    run = await db.get(GdocsImportRun, run_id)
    if run is None:
        return

    payload = run.payload or {}
    docs_in: dict = payload.get("docs") or {}
    rows_in: list = payload.get("rows") or []
    warnings: list[str] = list(payload.get("warnings") or [])
    keep_images = bool(payload.get("keepImages", True))

    def warn(msg: str) -> None:
        if len(warnings) < MAX_WARNINGS:
            warnings.append(msg)

    # ---- resolve provider/model once ----
    # A per-import override (chosen on the upload modal) wins; otherwise fall
    # back to the first-enabled provider and its default model. The endpoint
    # already validated an override is enabled + keyed, so this is just resolution.
    code = run.provider_code or await first_enabled_provider_code(db)
    if not code:
        await _fail(db, run, "No AI provider is enabled. Configure one in Settings first.")
        return
    provider: BaseProvider = await get_provider(db, code)
    model = run.model or provider.default_model
    if not model:
        await _fail(db, run, f"No model configured for provider '{code}'.")
        return

    # Admin-editable prompts (Brain → "gdocs_meta" / "gdocs_pairing"); fall
    # back to shipped defaults when unset.
    meta_prompt = await gdocs_meta_prompt(db)
    pairing_prompt = await gdocs_pairing_prompt(db)

    # ---- step 1: clean + meta per Doc ----
    crawlable = [
        (doc_id, d)
        for doc_id, d in docs_in.items()
        if isinstance(d, dict) and d.get("ok") and d.get("html")
    ]
    run.total_docs = len(crawlable)
    # processed[doc_id] -> {"title","content","seo_title","seo_description"}
    processed: dict[str, dict] = {}
    await db.commit()

    sem = asyncio.Semaphore(DOC_CONCURRENCY)

    async def _one_doc(doc_id: str, d: dict) -> tuple[str, dict | None, str | None]:
        async with sem:
            try:
                body = clean_doc_html(d.get("html") or "", keep_images=keep_images)
                meta = await extract_meta(
                    provider,
                    model,
                    doc_title=d.get("title") or "",
                    body_html=body,
                    system_prompt=meta_prompt,
                )
                note = None
                if meta.warnings:
                    note = f"Doc {doc_id}: " + "; ".join(meta.warnings)
                return doc_id, {
                    "title": d.get("title") or meta.seo_title,
                    "content": meta.body_html,
                    "seo_title": meta.seo_title,
                    "seo_description": meta.seo_description,
                }, note
            except Exception as exc:  # one bad doc shouldn't kill the run
                return doc_id, None, f"Doc {doc_id}: processing failed ({exc})"

    for i in range(0, len(crawlable), DOC_CHUNK):
        if await _is_cancelled(db, run_id):
            run = await db.get(GdocsImportRun, run_id)
            if run and run.finished_at is None:
                run.finished_at = _now()
                _clear_payload(run)
                await db.commit()
            return
        chunk = crawlable[i : i + DOC_CHUNK]
        results = await asyncio.gather(*(_one_doc(did, d) for did, d in chunk))
        done = failed = 0
        for doc_id, result, note in results:
            if result is None:
                failed += 1
            else:
                processed[doc_id] = result
                done += 1
            if note:
                warn(note)
        run = await db.get(GdocsImportRun, run_id)
        if run is None:
            return
        run.docs_done += done
        run.docs_failed += failed
        run.last_progress_at = _now()
        run.warnings = list(warnings)
        await db.commit()

    # Account for docs that the Apps Script couldn't export.
    for doc_id, d in docs_in.items():
        if not (isinstance(d, dict) and d.get("ok") and d.get("html")):
            err = d.get("error") if isinstance(d, dict) else "missing"
            warn(f"Doc {doc_id}: not exported ({err})")

    # ---- step 2: build one row per linked Doc ----
    # The sheet hyperlinks each written page's Doc onto its entry, so we build
    # ONE table row per link — not one per Structure page. Planned-but-unwritten
    # pages (no Doc link) never become empty rows. The slug comes from the
    # link's anchor (a URL path or a page name); title/content/meta come from
    # the linked Doc. There is no AI pairing step: the hyperlink IS the explicit
    # page↔Doc association, so nothing is guessed.
    built: list[dict] = []  # each: domain, language, label, title, content, seo_*
    used_slugs: set[tuple[str, str]] = set()  # (domain, slug) dedupe

    # Per-site structure (the full planned page list) — stored on the table for
    # the reference panel, and the coverage denominator. Built once up front.
    site_structure: list[dict] = []
    total_structure = 0
    total_links = 0
    for r in rows_in:
        links = r.get("links") or []
        total_links += len(links)
        # Real pages only — drop bracketed annotation lines like
        # "Teams (pillar page, not as a separate page)".
        structure = [
            s.strip()
            for s in (str(x) for x in (r.get("structure") or []))
            if is_page_entry(s)
        ]
        total_structure += len(structure)
        if structure:
            site_structure.append(
                {
                    "domain": (r.get("domain") or "").strip(),
                    "language": (r.get("language") or "").strip(),
                    "structure": structure,
                }
            )
        if not links:
            warn(
                f"Row {r.get('rowNumber')}: site "
                f"'{(r.get('domain') or '').strip() or 'no domain'}' had no "
                f"linked Docs — no rows created for it."
            )

    # Coverage: how many planned pages actually have a written Doc. The run
    # page shows the summary in its own banner (from the counters); here we only
    # log the *low-coverage* warning — the run-15 symptom where writers haven't
    # linked Docs onto Structure yet — so it isn't silently built near-empty.
    if total_structure > 0 and total_links < total_structure / 2:
        warn(
            f"⚠ Only {total_links} of {total_structure} Structure pages "
            f"have a linked Doc — the other {total_structure - total_links} "
            f"have no content yet. If you expected more, check that each "
            f"page's Doc is hyperlinked onto its Structure entry."
        )

    run = await db.get(GdocsImportRun, run_id)
    run.total_pages = total_links
    run.total_structure_pages = total_structure
    run.warnings = list(warnings)
    await db.commit()

    # Each site is paired independently (its Docs ↔ its Structure), one AI call
    # per site, bounded concurrency. The Structure entry is the slug source of
    # truth — the anchor is only a weak hint the model may ignore. Bracketed
    # annotation lines ("(pillar page…)") are excluded as slug candidates.
    # Pairing is one AI call per site; keep concurrency low so free-tier
    # providers don't rate-limit (a 429 used to drop a whole site's docs).
    matched = unmatched = 0
    psem = asyncio.Semaphore(3)

    async def _build_site(r: dict) -> tuple[list[dict], int, int, list[str]]:
        domain = (r.get("domain") or "").strip()
        language = (r.get("language") or "").strip()
        candidates = [
            s.strip()
            for s in (str(x) for x in (r.get("structure") or []))
            if is_page_entry(s)
        ]
        # Unique Docs in this site, in first-seen order.
        site_links: list[dict] = []
        seen_in_row: set[str] = set()
        for lk in r.get("links") or []:
            did = lk.get("docId")
            if not did or did in seen_in_row:
                continue
            seen_in_row.add(did)
            site_links.append(lk)

        # Homepage is handled deterministically (never sent to the AI): a Doc
        # whose anchor is a home token ("Home", "Homepage", "/") maps to the
        # Structure's home entry. That entry is then reserved so the AI can't
        # reassign it. Everything else is paired by the AI on the anchor.
        home_idx = next(
            (i for i, s in enumerate(candidates) if slug_from_link(s) == "home"),
            None,
        )
        pre_assigned: dict[str, int] = {}
        home_used = False
        ai_links: list[dict] = []
        for lk in site_links:
            anchor = (lk.get("label") or "").strip()
            if (
                not home_used
                and home_idx is not None
                and slug_from_link(anchor) == "home"
            ):
                pre_assigned[lk["docId"]] = home_idx
                home_used = True
            else:
                ai_links.append(lk)

        docs_to_pair = [
            DocToPair(
                doc_id=lk["docId"],
                anchor=(lk.get("label") or "").strip(),
                title=(processed.get(lk["docId"]) or {}).get("seo_title")
                or (processed.get(lk["docId"]) or {}).get("title")
                or "",
            )
            for lk in ai_links
        ]
        mapping: dict[str, int | None] = {}
        if docs_to_pair:
            async with psem:
                mapping = await pair_docs_to_structure(
                    provider,
                    model,
                    structure=candidates,
                    docs=docs_to_pair,
                    system_prompt=pairing_prompt,
                )

        site_built: list[dict] = []
        m = u = 0
        notes: list[str] = []
        for lk in site_links:
            did = lk["docId"]
            label = (lk.get("label") or "").strip()
            doc = processed.get(did)
            idx = pre_assigned.get(did)
            if idx is None:
                ai_idx = mapping.get(did)
                # Don't let the AI grab the home entry reserved above.
                if ai_idx is not None and not (home_used and ai_idx == home_idx):
                    idx = ai_idx
            if idx is not None and 0 <= idx < len(candidates):
                slug_base = slug_from_link(candidates[idx])
            else:
                slug_base = NO_EXACT_SLUG
                notes.append(
                    f"Row {r.get('rowNumber')}: Doc '{label or did}' "
                    f"({domain or 'no domain'}) couldn't be matched to a "
                    f"Structure page — imported as '{NO_EXACT_SLUG}'."
                )
            if doc is not None:
                m += 1
            else:
                u += 1
                notes.append(
                    f"Row {r.get('rowNumber')}: '{label or did}' "
                    f"({domain or 'no domain'}) — its Doc could not be "
                    f"exported; row added with empty content."
                )
            site_built.append(
                {
                    "domain": domain,
                    "language": language,
                    "label": label,
                    "slug_base": slug_base,
                    "title": (doc or {}).get("title") or label,
                    "content": (doc or {}).get("content") or "",
                    "seo_title": (doc or {}).get("seo_title") or "",
                    "seo_description": (doc or {}).get("seo_description") or "",
                }
            )
        return site_built, m, u, notes

    for i in range(0, len(rows_in), ROW_CHUNK):
        if await _is_cancelled(db, run_id):
            run = await db.get(GdocsImportRun, run_id)
            if run and run.finished_at is None:
                run.finished_at = _now()
                _clear_payload(run)
                await db.commit()
            return
        chunk = rows_in[i : i + ROW_CHUNK]
        results = await asyncio.gather(*(_build_site(r) for r in chunk))
        for site_built, m, u, notes in results:
            built.extend(site_built)
            matched += m
            unmatched += u
            for n in notes:
                warn(n)
        run = await db.get(GdocsImportRun, run_id)
        run.pages_matched = matched
        run.pages_unmatched = unmatched
        run.last_progress_at = _now()
        run.warnings = list(warnings)
        await db.commit()

    # ---- step 3: build the bulk table ----
    mode = decide_mode([b["domain"] for b in built])
    layout = column_layout(mode)

    table = BulkTable(
        name=run.table_name,
        created_by_id=run.created_by_id,
        folder_id=run.target_folder_id,
        description="Imported from Google Docs",
        gdocs_structure=site_structure or None,
    )
    db.add(table)
    await db.flush()

    columns: dict[str, BulkTableColumn] = {}  # field_key (or name) -> column
    for pos, (name, field_key) in enumerate(layout):
        col = BulkTableColumn(table_id=table.id, position=pos, name=name, kind="input")
        db.add(col)
        columns[field_key or name] = col
    await db.flush()

    # Assign per-(domain) unique slugs, then create rows + cells. Also record a
    # per-row slug audit (raw anchor → final slug) for the review panel.
    row_objs: list[BulkTableRow] = []
    slug_audit: list[dict] = []
    for pos, b in enumerate(built):
        slug = b.get("slug_base") or slug_from_link(b["label"], fallback=f"page-{pos + 1}")
        base = slug
        n = 2
        while (b["domain"], slug) in used_slugs:
            slug = f"{base}-{n}"
            n += 1
        used_slugs.add((b["domain"], slug))
        b["slug"] = slug
        anchor = b["label"]
        slug_audit.append(
            {
                "row": pos + 1,
                "domain": b["domain"],
                "language": b["language"],
                "seo_title": b["seo_title"] or b["title"],
                "anchor": anchor,
                "slug": slug,
                # 'changed' = the AI/structure slug differs from what the anchor
                # alone would have produced; 'unmatched' = no Structure pairing.
                "changed": slug_from_link(anchor) != base,
                "unmatched": base == NO_EXACT_SLUG,
            }
        )
        row = BulkTableRow(table_id=table.id, position=pos)
        db.add(row)
        row_objs.append(row)
    await db.flush()
    table.gdocs_slug_audit = slug_audit or None

    def cell(row_id: int, col: BulkTableColumn, value: str) -> None:
        if value:
            db.add(
                BulkTableCell(
                    row_id=row_id, column_id=col.id, value=value, status="manual"
                )
            )

    for b, row in zip(built, row_objs):
        if mode == "multi":
            cell(row.id, columns["domain"], b["domain"])
        cell(row.id, columns["lang"], b["language"])
        cell(row.id, columns["slug"], b["slug"])
        cell(row.id, columns["title"], b["title"])
        cell(row.id, columns["content"], b["content"])
        cell(row.id, columns["seo_title"], b["seo_title"])
        cell(row.id, columns["seo_description"], b["seo_description"])
        # Post ID / Post URL intentionally left blank.

    run = await db.get(GdocsImportRun, run_id)
    if run.status == "cancelled":
        # A cancel landed during the build; honor it but the table already
        # exists, so still record it.
        run.result_table_id = table.id
        run.mode = mode
        run.rows_built = len(built)
        run.warnings = list(warnings)
        if run.finished_at is None:
            run.finished_at = _now()
        _clear_payload(run)
        await db.commit()
        return

    run.result_table_id = table.id
    run.mode = mode
    run.rows_built = len(built)
    run.warnings = list(warnings)
    run.status = "done"
    run.finished_at = _now()
    run.last_progress_at = _now()
    _clear_payload(run)
    await db.commit()


@celery_app.task(name="gdocs_import.watchdog")
def gdocs_import_watchdog() -> dict:
    asyncio.run(_with_session(_watchdog))
    return {"ok": True}


async def _watchdog(db: AsyncSession) -> None:
    """Fail runs that have stalled — a worker restart/crash or a lost broker
    message leaves no exception for ``_run``'s guard to catch, so the run
    sits on 'running' (or never leaves 'queued') forever.

    Unlike the link-checker (chunked + resumable), a gdocs import is one
    monolithic task: a stall means it's dead, so we mark it failed rather
    than resume. ``STUCK_MINUTES`` is generous so a legitimately slow run
    (many AI calls between progress commits) is never killed mid-flight."""
    rows = (
        (
            await db.execute(
                select(GdocsImportRun).where(
                    text(
                        "(status = 'running' AND "
                        " (last_progress_at IS NULL OR last_progress_at < "
                        f"  now() - interval '{STUCK_MINUTES} minutes')) "
                        "OR (status = 'queued' AND created_at < "
                        f"   now() - interval '{STUCK_MINUTES} minutes')"
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for run in rows:
        run.status = "failed"
        run.error = (
            "Import timed out — the worker stopped reporting progress "
            "(likely a worker restart or crash). Re-upload to try again."
        )
        if run.finished_at is None:
            run.finished_at = _now()
        _clear_payload(run)
    if rows:
        await db.commit()
        logger.warning("gdocs_import watchdog failed %d stuck run(s)", len(rows))
