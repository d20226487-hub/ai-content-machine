"""Shared helpers for applying a link-fix run's result.

Both the AI fix (Celery, ``app/tasks/link_fix.py``) and the deterministic
Translation-links replace job (synchronous, in the API) need to:

  * gather the EXPECTED links for a row — read from the snapshotted expected
    columns, or recomputed from a translation run's ``translation_config``;
  * re-verify the corrected cells IN PLACE — re-juxtapose each touched cell and
    stamp the originating check run's violations ``solved`` / ``unsolved`` so
    the run page (and the translation overview) can show what the fix did.

Kept here (not in the Celery task module) so the API can import them without
pulling in Celery.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BulkTableCell,
    LinkCheckRun,
    LinkCheckViolation,
    LinkFixCell,
    LinkFixRun,
)
from app.services.link_check import (
    extract_expected_links,
    extract_output_links,
    juxtapose,
    normalize_link,
)
from app.services.translation_links import compute_expected_links, parse_domains


async def expected_links_for_row(
    db: AsyncSession, *, run: LinkFixRun, row_id: int
) -> list[str]:
    """Expected links for one row.

    Translation runs have no materialized expected column — recompute the
    localized expected links from the source run's ``translation_config`` (read
    the row's original/lang/domain cells). Normal runs read the snapshotted
    expected columns. ``db.get`` on the source run is identity-mapped, so this
    stays one extra query per session."""
    cfg = None
    if run.source_run_id:
        source = await db.get(LinkCheckRun, run.source_run_id)
        cfg = source.translation_config if source else None

    if cfg:
        orig_col = int(cfg["original_column_id"])
        lang_col = int(cfg["lang_column_id"])
        domain_cols = [int(c) for c in cfg.get("internal_domain_column_ids", [])]
        rows = (
            await db.execute(
                select(BulkTableCell.column_id, BulkTableCell.value).where(
                    BulkTableCell.row_id == row_id,
                    BulkTableCell.column_id.in_([orig_col, lang_col, *domain_cols]),
                )
            )
        ).all()
        vals = {cid: val for cid, val in rows}
        lang = (vals.get(lang_col) or "").strip()
        if not lang:
            return []
        internal_domains: list[str] = []
        for dc in domain_cols:
            internal_domains += parse_domains(vals.get(dc))
        return compute_expected_links(
            vals.get(orig_col),
            lang,
            internal_domains=internal_domains,
            product_domains=cfg.get("product_domains", []),
            exceptions=cfg.get("exceptions", []),
            internal_treatment=cfg.get("internal_treatment", "skip"),
            external_treatment=cfg.get("external_treatment", "skip"),
            default_langs=cfg.get("product_default_langs", {}) or {},
        )

    exp_cols = [int(c) for c in (run.expected_column_ids or [])]
    if not exp_cols:
        return []
    cells = (
        (
            await db.execute(
                select(BulkTableCell.value).where(
                    BulkTableCell.row_id == row_id,
                    BulkTableCell.column_id.in_(exp_cols),
                )
            )
        )
        .scalars()
        .all()
    )
    out: list[str] = []
    for v in cells:
        out += extract_expected_links(v)
    return out


async def reverify_in_place(db: AsyncSession, run: LinkFixRun) -> None:
    """Re-juxtapose the cells this run corrected and stamp the originating
    check run's violations. NULL stays = untouched; 'solved' = the flagged
    link is gone from the corrected cell, 'unsolved' = still present.

    Does not commit — the caller owns the transaction."""
    if run.source_run_id is None:
        return

    cells = (
        (
            await db.execute(
                select(LinkFixCell).where(
                    LinkFixCell.run_id == run.id,
                    LinkFixCell.state == "done",
                )
            )
        )
        .scalars()
        .all()
    )
    for cell in cells:
        target_col = run.target_column_id or cell.column_id
        corrected = (
            await db.execute(
                select(BulkTableCell.value).where(
                    BulkTableCell.row_id == cell.row_id,
                    BulkTableCell.column_id == target_col,
                )
            )
        ).scalar_one_or_none()

        expected = await expected_links_for_row(db, run=run, row_id=cell.row_id)

        omitted, hallucinated = juxtapose(extract_output_links(corrected), expected)
        still = {normalize_link(u) for u in omitted + hallucinated}

        violations = (
            (
                await db.execute(
                    select(LinkCheckViolation).where(
                        LinkCheckViolation.run_id == run.source_run_id,
                        LinkCheckViolation.row_id == cell.row_id,
                        LinkCheckViolation.column_id == cell.column_id,
                        LinkCheckViolation.problem.in_(("omitted", "hallucinated")),
                    )
                )
            )
            .scalars()
            .all()
        )
        for v in violations:
            v.resolution = "unsolved" if normalize_link(v.link) in still else "solved"
