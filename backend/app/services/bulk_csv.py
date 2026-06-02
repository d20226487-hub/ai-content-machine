"""Render a bulk table to CSV text.

Shared by the authenticated export endpoint (`GET
/library/tables/{id}/export.csv`) and the public Autotool endpoint
(`GET /autotool/{token}.csv`).

``single_line=True`` (used by Autotool) collapses any line breaks *inside* a
cell to a single space so every table row is one physical line — generated
content (HTML) often contains newlines, which standard CSV preserves as
multi-line quoted fields and a naive consumer can't parse. The authenticated
export leaves cells untouched (RFC 4180 multi-line quoted fields, exact
content).
"""
import csv
import io
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BulkTable, BulkTableCell

_NEWLINES = re.compile(r"[\r\n]+")


async def build_table_csv(
    db: AsyncSession,
    table: BulkTable,
    *,
    single_line: bool = False,
    include_row_ids: set[int] | None = None,
) -> str:
    """Render ``table`` (must be loaded with ``columns`` + ``rows``) to CSV.

    Column names form the header row; each data row is filled by looking up
    the cell value at every (row_id, column_id) coordinate, defaulting to an
    empty string where no cell exists. When ``single_line`` is set, runs of
    CR/LF inside a value are replaced with a single space so each row occupies
    exactly one physical line. When ``include_row_ids`` is given, only those
    rows are emitted (used to serve one Autotool file per domain).
    """

    def render(value: str | None) -> str:
        s = value or ""
        return _NEWLINES.sub(" ", s) if single_line else s

    emit_rows = [
        r
        for r in table.rows
        if include_row_ids is None or r.id in include_row_ids
    ]

    cells = []
    if emit_rows:
        cells = (
            (
                await db.execute(
                    select(BulkTableCell).where(
                        BulkTableCell.row_id.in_([r.id for r in emit_rows])
                    )
                )
            )
            .scalars()
            .all()
        )
    lookup = {(c.row_id, c.column_id): render(c.value) for c in cells}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([render(c.name) for c in table.columns])
    for r in emit_rows:
        writer.writerow([lookup.get((r.id, c.id), "") for c in table.columns])
    return buf.getvalue()
