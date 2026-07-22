"""Build a bulk table from CSV bytes — shared by the authenticated multipart
import (``POST /library/tables/import-csv``) and the machine-to-machine ingest
endpoint (``POST /ingest/csv-tables``).

Kept deliberately transport-agnostic: it takes raw bytes + options and does the
decode / parse / create, so the API layer only worries about auth, where the
bytes come from (a multipart file vs the raw request body), and shaping the
response. Behaviour matches the original inline import exactly — BOM-tolerant
decode with a latin-1 fallback, blank cells skipped, extra fields past the
header ignored, and bulk INSERTs (no per-row flush) so a multi-MB file lands in
a couple of seconds instead of timing out.
"""
from __future__ import annotations

import csv
import io

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BulkTable, BulkTableCell, BulkTableColumn, BulkTableRow

# 200 MB — matches the multipart import cap. The reverse proxy has its own
# inbound body limit (raise both together if you need larger files).
MAX_CSV_UPLOAD = 200 * 1024 * 1024
# Cells per bulk INSERT — bounds statement + memory size on huge files.
_CSV_CELL_BATCH = 5000


class CsvImportError(ValueError):
    """Bad CSV input (empty / too big / undecodable / malformed). The API layer
    maps this to a 400 with the message."""


def normalize_delimiter(delimiter: str) -> str:
    """Accept the UI's escaped-tab (`"\\t"`) as well as a real tab, and reject
    anything that isn't a single character."""
    if delimiter in ("\\t", "\t"):
        return "\t"
    if len(delimiter) != 1:
        raise CsvImportError("Delimiter must be a single character.")
    return delimiter


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")  # tolerate a UTF-8 BOM
    except UnicodeDecodeError:
        try:
            return raw.decode("latin-1")
        except UnicodeDecodeError:
            raise CsvImportError("The file is not valid text.")


async def build_table_from_csv(
    db: AsyncSession,
    *,
    name: str,
    raw: bytes,
    delimiter: str = ",",
    has_header: bool = True,
    folder_id: int | None = None,
    created_by_id: int | None = None,
) -> BulkTable:
    """Parse ``raw`` CSV bytes and create a bulk table (+ columns, rows, cells).

    Commits and returns the new ``BulkTable``. Raises ``CsvImportError`` (→ 400)
    on bad input. The caller owns name validation, folder verification, and the
    response shape.
    """
    if not raw:
        raise CsvImportError("The CSV is empty.")
    if len(raw) > MAX_CSV_UPLOAD:
        raise CsvImportError(
            f"File too large (max {MAX_CSV_UPLOAD // (1024 * 1024)} MB)."
        )
    delimiter = normalize_delimiter(delimiter)
    text_data = _decode(raw)

    reader = csv.reader(io.StringIO(text_data), delimiter=delimiter)
    rows = [r for r in reader]
    if not rows:
        raise CsvImportError("The CSV is empty.")

    if has_header:
        headers = [h.strip() or f"Column {i + 1}" for i, h in enumerate(rows[0])]
        data_rows = rows[1:]
    else:
        col_count = max(len(r) for r in rows)
        headers = [f"Column {i + 1}" for i in range(col_count)]
        data_rows = rows

    t = BulkTable(name=name, created_by_id=created_by_id, folder_id=folder_id)
    db.add(t)
    await db.flush()

    column_objs = [
        BulkTableColumn(table_id=t.id, position=i, name=h, kind="input")
        for i, h in enumerate(headers)
    ]
    db.add_all(column_objs)
    await db.flush()  # one round-trip populates every column id

    if data_rows:
        await db.execute(
            pg_insert(BulkTableRow).values(
                [{"table_id": t.id, "position": ri} for ri in range(len(data_rows))]
            )
        )
        id_by_pos = {
            pos: rid
            for rid, pos in (
                await db.execute(
                    select(BulkTableRow.id, BulkTableRow.position).where(
                        BulkTableRow.table_id == t.id
                    )
                )
            ).all()
        }
        col_ids = [c.id for c in column_objs]
        cell_payload: list[dict] = []
        for ri, row_values in enumerate(data_rows):
            rid = id_by_pos[ri]
            for ci, val in enumerate(row_values):
                if ci >= len(col_ids):
                    break  # ignore extra fields
                value = (val or "").strip()
                if value == "":
                    continue
                cell_payload.append(
                    {
                        "row_id": rid,
                        "column_id": col_ids[ci],
                        "value": value,
                        "status": "manual",
                    }
                )
        for i in range(0, len(cell_payload), _CSV_CELL_BATCH):
            await db.execute(
                pg_insert(BulkTableCell).values(cell_payload[i : i + _CSV_CELL_BATCH])
            )

    await db.commit()
    return t
