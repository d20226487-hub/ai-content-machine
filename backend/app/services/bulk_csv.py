"""Render a bulk table to CSV text.

Shared by the authenticated export endpoint (`GET
/library/tables/{id}/export.csv`) and the public Autotool endpoint
(`GET /autotool/{token}.csv`) so both produce byte-identical output.
"""
import csv
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BulkTable, BulkTableCell


async def build_table_csv(db: AsyncSession, table: BulkTable) -> str:
    """Render ``table`` (must be loaded with ``columns`` + ``rows``) to CSV.

    Column names form the header row; each data row is filled by looking up
    the cell value at every (row_id, column_id) coordinate, defaulting to an
    empty string where no cell exists.
    """
    cells = []
    if table.rows:
        cells = (
            (
                await db.execute(
                    select(BulkTableCell).where(
                        BulkTableCell.row_id.in_([r.id for r in table.rows])
                    )
                )
            )
            .scalars()
            .all()
        )
    lookup = {(c.row_id, c.column_id): c.value or "" for c in cells}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c.name for c in table.columns])
    for r in table.rows:
        writer.writerow([lookup.get((r.id, c.id), "") for c in table.columns])
    return buf.getvalue()
