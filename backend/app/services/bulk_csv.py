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
from collections.abc import AsyncIterator

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BulkTable, BulkTableCell, BulkTableRow
from app.db.session import SessionLocal

_NEWLINES = re.compile(r"[\r\n]+")

# Rows per DB round-trip when streaming a large table. Keeps peak memory to one
# batch of cells + one CSV chunk, regardless of total table size.
_EXPORT_BATCH_ROWS = 1000


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


def _csv_chunk(rows: list[list[str]]) -> str:
    """Render a batch of already-shaped rows to a CSV string fragment.

    Uses the same default ``csv.writer`` dialect as ``build_table_csv`` so the
    streamed output is byte-for-byte the format of the old in-memory export
    (RFC 4180, ``\\r\\n`` line terminators, minimal quoting).
    """
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue()


async def stream_table_csv(
    table_id: int,
    columns: list[tuple[int, str]],
    *,
    batch_rows: int = _EXPORT_BATCH_ROWS,
) -> AsyncIterator[str]:
    """Stream a bulk table to CSV in row-batches, keeping memory flat.

    Backs the authenticated export endpoint for tables too large to build in
    memory (the old path loaded every row + cell + the whole string + a gzip
    copy, blowing past the prod api memory cap above ~70 MB). ``columns`` is the
    ordered ``[(column_id, name), ...]`` header, already resolved by the caller
    from the request session.

    Opens its OWN session (``SessionLocal`` on the shared engine): a
    ``StreamingResponse`` body is consumed AFTER the endpoint returns, by which
    point the request-scoped session is closed. Rows are walked by keyset on
    ``(position, id)`` — both NOT NULL — so paging stays index-friendly and
    deterministic, matching the on-screen order (the ``rows`` relationship
    orders by ``position``). Cells are fetched one batch at a time as plain
    ``(row_id, column_id, value)`` tuples (not full ORM objects).
    """
    col_ids = [cid for cid, _ in columns]
    # Header row first — bytes start flowing immediately, so the reverse proxy
    # sees data within its read/write timeout instead of waiting for the whole
    # response to be built.
    yield _csv_chunk([[name for _, name in columns]])

    async with SessionLocal() as db:
        last_pos: int | None = None
        last_id: int | None = None
        while True:
            q = select(BulkTableRow.id, BulkTableRow.position).where(
                BulkTableRow.table_id == table_id
            )
            if last_id is not None:
                q = q.where(
                    tuple_(BulkTableRow.position, BulkTableRow.id)
                    > tuple_(last_pos, last_id)
                )
            q = q.order_by(BulkTableRow.position, BulkTableRow.id).limit(batch_rows)
            batch = (await db.execute(q)).all()
            if not batch:
                break

            row_ids = [r.id for r in batch]
            cells = (
                await db.execute(
                    select(
                        BulkTableCell.row_id,
                        BulkTableCell.column_id,
                        BulkTableCell.value,
                    ).where(BulkTableCell.row_id.in_(row_ids))
                )
            ).all()
            lookup = {(rid, cid): (val or "") for rid, cid, val in cells}

            yield _csv_chunk(
                [[lookup.get((rid, cid), "") for cid in col_ids] for rid in row_ids]
            )
            last_pos, last_id = batch[-1].position, batch[-1].id
