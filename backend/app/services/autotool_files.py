"""Per-domain Autotool file tokens + row resolution.

Autotool needs ONE file per target site (it publishes a whole file's rows to
the site(s) in the POST). So a shared table is split by its site/domain column:
each distinct domain becomes its own ``file`` whose CSV contains only that
domain's rows.

To avoid storing a token per (table, domain), the per-domain ``file`` is a
*composite* token the public route decodes on the fly:

    <table_token>~<site_column_id>~<urlsafe_b64(domain)>

The table_token (unguessable uuid hex) keeps the whole thing unguessable; the
column id + encoded domain tell the route how to filter. A plain table token
(no '~') still serves the full table, for back-compat / debugging.

Pure helpers only (no httpx/crypto) so both the public CSV route and the
authenticated preview can import them without pulling in the config service.
"""
from __future__ import annotations

import base64

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BulkTableCell, BulkTableRow

_SEP = "~"


def encode_file_token(table_token: str, column_id: int, domain: str) -> str:
    b64 = base64.urlsafe_b64encode(domain.encode()).decode().rstrip("=")
    return f"{table_token}{_SEP}{column_id}{_SEP}{b64}"


def decode_file_token(token: str) -> tuple[str, int, str] | None:
    """Return (table_token, column_id, domain) for a composite token, else None."""
    parts = token.split(_SEP)
    if len(parts) != 3:
        return None
    table_token, col_raw, b64 = parts
    try:
        column_id = int(col_raw)
    except ValueError:
        return None
    pad = "=" * (-len(b64) % 4)
    try:
        domain = base64.urlsafe_b64decode((b64 + pad).encode()).decode()
    except Exception:
        return None
    return table_token, column_id, domain


async def column_value_counts(
    db: AsyncSession, table_id: int, column_id: int
) -> list[tuple[str, int]]:
    """Distinct non-empty values of a column with their row counts.

    Order-preserving (first appearance). Values are stripped so they match the
    domain encoded into per-domain tokens.
    """
    values = (
        (
            await db.execute(
                select(BulkTableCell.value)
                .join(BulkTableRow, BulkTableCell.row_id == BulkTableRow.id)
                .where(
                    BulkTableRow.table_id == table_id,
                    BulkTableCell.column_id == column_id,
                )
                .order_by(BulkTableRow.position, BulkTableRow.id)
            )
        )
        .scalars()
        .all()
    )
    counts: dict[str, int] = {}
    for v in values:
        s = (v or "").strip()
        if s:
            counts[s] = counts.get(s, 0) + 1
    return list(counts.items())


async def rows_for_domain(
    db: AsyncSession, table_id: int, column_id: int, domain: str
) -> set[int]:
    """Ids of rows whose ``column_id`` cell (stripped) equals ``domain``."""
    pairs = (
        await db.execute(
            select(BulkTableCell.row_id, BulkTableCell.value)
            .join(BulkTableRow, BulkTableCell.row_id == BulkTableRow.id)
            .where(
                BulkTableRow.table_id == table_id,
                BulkTableCell.column_id == column_id,
            )
        )
    ).all()
    return {rid for rid, val in pairs if (val or "").strip() == domain}
