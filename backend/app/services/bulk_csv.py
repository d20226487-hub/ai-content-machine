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
import gzip
import io
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import quote

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BulkTable, BulkTableCell, BulkTableRow
from app.db.session import SessionLocal

_NEWLINES = re.compile(r"[\r\n]+")


def content_disposition(filename: str, *, inline: bool = False) -> str:
    """Build a Content-Disposition value that survives non-ASCII filenames.

    Starlette encodes header values as latin-1, so a Cyrillic (or any
    non-latin-1) filename passed as a bare ``filename="..."`` raises
    UnicodeEncodeError and 500s the whole response — which is exactly what a
    Russian-named table's CSV download hit. We emit an ASCII-only fallback plus
    an RFC 5987 ``filename*=UTF-8''`` so modern browsers show the real name and
    the header always encodes cleanly. The fallback uses an explicit
    ``isascii()`` guard because ``str.isalnum()`` is Unicode-aware (it's what let
    Cyrillic through the old sanitizer in the first place).
    """
    disposition = "inline" if inline else "attachment"
    ascii_fallback = (
        "".join(
            ch if (ch.isascii() and (ch.isalnum() or ch in "._-")) else "_"
            for ch in filename
        ).strip("_")
        or "table.csv"
    )
    return (
        f'{disposition}; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )

# Rows per DB round-trip when streaming a large table. Keeps peak memory to one
# batch of cells + one CSV chunk, regardless of total table size.
_EXPORT_BATCH_ROWS = 1000


async def build_table_csv(
    db: AsyncSession,
    table: BulkTable,
    *,
    single_line: bool = False,
    include_row_ids: set[int] | None = None,
    include_column_ids: set[int] | None = None,
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

    # Column subset (used by Autotool to drop helper columns); None = all.
    emit_cols = [
        c
        for c in table.columns
        if include_column_ids is None or c.id in include_column_ids
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([render(c.name) for c in emit_cols])
    for r in emit_rows:
        writer.writerow([lookup.get((r.id, c.id), "") for c in emit_cols])
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


async def _csv_body_chunks(
    db: AsyncSession,
    table_id: int,
    col_ids: list[int],
    batch_rows: int,
) -> AsyncIterator[tuple[str, int]]:
    """Yield ``(csv_fragment, rows_in_fragment)`` for the table BODY (no header).

    Walks rows by keyset on ``(position, id)`` — both NOT NULL — so paging stays
    index-friendly and deterministic, matching the on-screen order (the ``rows``
    relationship orders by ``position``). Cells are fetched one batch at a time
    as plain ``(row_id, column_id, value)`` tuples (not full ORM objects).
    Shared by the HTTP streamer and the background-export gzip builder.
    """
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
        yield (
            _csv_chunk(
                [[lookup.get((rid, cid), "") for cid in col_ids] for rid in row_ids]
            ),
            len(batch),
        )
        last_pos, last_id = batch[-1].position, batch[-1].id


async def stream_table_csv(
    table_id: int,
    columns: list[tuple[int, str]],
    *,
    batch_rows: int = _EXPORT_BATCH_ROWS,
) -> AsyncIterator[str]:
    """Stream a bulk table to CSV in row-batches, keeping memory flat.

    Backs the authenticated export endpoint. ``columns`` is the ordered
    ``[(column_id, name), ...]`` header, resolved by the caller. Opens its OWN
    session (``SessionLocal``): a ``StreamingResponse`` body is consumed AFTER
    the endpoint returns, when the request-scoped session is already closed.
    """
    col_ids = [cid for cid, _ in columns]
    # Header first — bytes start flowing immediately.
    yield _csv_chunk([[name for _, name in columns]])
    async with SessionLocal() as db:
        async for chunk, _n in _csv_body_chunks(db, table_id, col_ids, batch_rows):
            yield chunk


async def build_table_csv_gzip(
    db: AsyncSession,
    table_id: int,
    columns: list[tuple[int, str]],
    *,
    batch_rows: int = _EXPORT_BATCH_ROWS,
    on_progress: Callable[[int], Awaitable[None]] | None = None,
) -> tuple[bytes, int]:
    """Build the full table CSV and return ``(gzipped_bytes, rows_written)``.

    Used by the background-export worker. Memory stays bounded: rows are pulled
    one batch at a time and fed into an incremental gzip stream, so only the
    growing COMPRESSED buffer (~1/5 of the CSV) plus one batch is held. Calls
    ``on_progress(rows_written)`` after each batch (the caller throttles how
    often it persists). Uses the caller's session (the worker owns its lifecycle).
    """
    col_ids = [cid for cid, _ in columns]
    buf = io.BytesIO()
    gz = gzip.GzipFile(fileobj=buf, mode="wb")
    gz.write(_csv_chunk([[name for _, name in columns]]).encode("utf-8"))
    rows_written = 0
    async for chunk, n in _csv_body_chunks(db, table_id, col_ids, batch_rows):
        gz.write(chunk.encode("utf-8"))
        rows_written += n
        if on_progress is not None:
            await on_progress(rows_written)
    gz.close()
    return buf.getvalue(), rows_written
