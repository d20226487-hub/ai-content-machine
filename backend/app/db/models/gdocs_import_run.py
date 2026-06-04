"""GdocsImportRun — bookkeeping for the Google-Docs → Custom-CMS importer.

A run is created from an uploaded JSON file (produced by the Apps Script in
``tools/gdocs-import``). The file carries the sheet rows (domain, language,
page Structure, Doc links) plus each linked Doc exported to HTML. The Celery
task cleans every Doc, extracts its meta, pairs each Structure page to a Doc,
and builds a bulk table in the Custom-CMS publishing layout (single- or
multi-site, decided by the number of distinct domains).

Because Doc cleaning + AI meta/pairing is slow over hundreds of Docs, the work
runs in a background task with live progress (status + counters), mirroring the
Link Checker / Structure-Format runs. See migration 0048.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GdocsImportRun(Base):
    __tablename__ = "gdocs_import_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # queued → running → (done | failed | cancelled)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # Name for the bulk table this run builds (also the run's display label).
    table_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Where to file the resulting table (NULL = root). Plain int, no FK — a
    # folder delete shouldn't cascade away run history.
    target_folder_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 'single' | 'multi' — decided from the distinct domain count at build time.
    # NULL until the run reaches the build step.
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Per-import AI override (migration 0049). NULL = fall back to the
    # first-enabled provider and its default model. ``provider_code`` matches
    # ``providers.code``; ``model`` is a free-form model id from that provider's
    # available list. Chosen on the upload modal; consumed by the task when it
    # resolves which LLM cleans meta + pairs pages.
    provider_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # The full uploaded JSON contract (rows + docs + columns + warnings). Large
    # (Doc HTML lives here) — only needed while the job runs. The task nulls it
    # to ``{}`` once the run reaches a terminal state (done/failed/cancelled,
    # including watchdog-failed) so finished rows + DB backups stay small. The
    # counters/warnings/error on this row remain the durable history.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # The bulk table this run produced. SET NULL so deleting the table doesn't
    # delete the run record. NULL until the build step completes.
    result_table_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="SET NULL"), nullable=True
    )

    # Progress counters.
    total_docs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_unmatched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # How many Structure entries the upload listed across all sites — the
    # "planned pages" denominator for the run page's coverage report. ``total_pages``
    # (links) is the numerator. See migration 0050.
    total_structure_pages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # Rows written to the resulting table (set at build time).
    rows_built: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Aggregated, human-readable notes (Apps Script warnings + processing
    # warnings + unmatched-page notes). A JSON list of strings.
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_progress_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
