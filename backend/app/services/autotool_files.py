"""Per-domain, paged Autotool file tokens + row resolution.

Autotool needs ONE file per target site, and — because the importer runs under
a finite (~60s) PHP execution window — each file is further capped to a page of
``page_size`` rows (operator-controlled, default ``DEFAULT_PAGE_SIZE``). So a
shared table is split first by its site/domain column, then each domain's rows
are split into pages: every (domain, page) pair becomes its own ``file`` whose
CSV holds just that page's rows.

To avoid storing a token per (table, domain, page), the ``file`` packs the
table token, the site column id, the page start offset, the page size, and the
domain into ONE path segment using **only ASCII letters and digits** — the
external Autotool proxy that downloads the CSV rejects every other character
(and wants no ``.csv`` on the value it receives). The layout is positional hex,
**table token first** so a consumer can read the table id straight off the
front (the proxy does):

    <table_token: 32 hex><column_id: 8 hex><start: 8 hex><limit: 8 hex><domain: hex>

e.g. table e42235…348a + column 304 + start 0 + size 50 + "mundialenvivo.net" →
    e42235af2c6643609313d4c86a8d348a 00000130 00000000 00000032 6d756e…6574  (sans spaces)

Encoding the page size into the token keeps the public route self-describing:
it slices ``ordered[start : start + limit]`` straight from the token, with no
shared page-size constant to keep in sync. Every part is ``[0-9a-f]``, so the
whole token is lowercase hex — alphanumeric for ANY domain (incl. URLs /
non-ASCII). Hex, not base64, precisely because base64 emits ``-``/``_``
(urlsafe) or ``+``/``/`` (standard) for some inputs, which the proxy forbids.
The fixed widths make it self-delimiting; a bare 32-char table token (too short
to be composite) still serves the whole table, and length alone tells the two
apart. The legacy ``<table_token>~<col>~<urlsafe_b64(domain)>`` form (no paging)
is still decoded too, so any link already issued keeps resolving.

Pure helpers only (no httpx/crypto) so both the public CSV route and the
authenticated preview can import them without pulling in the config service.
"""
from __future__ import annotations

import base64
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BulkTable, BulkTableCell, BulkTableRow

DEFAULT_PAGE_SIZE = 50  # rows per file when the operator doesn't choose
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 1000  # guardrail — a too-large page defeats the importer's window

# ----- required columns -----
#
# Autotool's WordPress importer needs these four columns in every CSV it pulls.
# A table can't be exposed to Autotool (the public link) or sent (a run) unless
# all four are among the columns INCLUDED for Autotool — an unchecked required
# column counts as absent, since it never reaches the CSV. Matched by EXACT,
# case-insensitive, trimmed header name (the `domain` role also accepts `site`).
# Defined here, in the pure-helpers module, so the enable endpoint, the preview,
# the send run and any test can all import it without pulling in httpx/crypto.
# The frontend mirrors this list (frontend/lib/autotool.ts) — keep them in sync.
REQUIRED_AUTOTOOL_COLUMNS: tuple[tuple[str, frozenset[str]], ...] = (
    ("domain", frozenset({"domain", "site"})),
    ("post_type", frozenset({"post_type"})),
    ("slug", frozenset({"slug"})),
    ("status", frozenset({"status"})),
)


def missing_required_columns(column_names: Iterable[str]) -> list[str]:
    """Labels of the required Autotool roles NOT covered by ``column_names``.

    Match is exact, case-insensitive and trimmed. Pass the names of the columns
    that will actually be in the CSV — i.e. the operator's selected subset, not
    the whole table — so an unchecked required column is reported as missing.
    Empty result = all four requirements met. Order follows the spec above.
    """
    present = {(n or "").strip().lower() for n in column_names}
    return [
        label
        for label, accepted in REQUIRED_AUTOTOOL_COLUMNS
        if accepted.isdisjoint(present)
    ]


def required_columns_error(missing: list[str]) -> str:
    """A human error for a table missing required Autotool columns (see above)."""
    return (
        "This table is missing columns Autotool requires: "
        + ", ".join(missing)
        + ". Add them to the table and include them for Autotool."
    )


_SEP = "~"  # legacy delimiter only — see _decode_legacy
_TT_LEN = 32  # uuid4().hex
_COL_HEX = 8  # 8 hex digits cover column ids up to 0xFFFFFFFF (~4.3B)
_START_HEX = 8  # 8 hex digits cover start offsets up to 0xFFFFFFFF rows
_LIMIT_HEX = 8  # page size (rows per file), same fixed width
_MIN_COMPOSITE = (
    _TT_LEN + _COL_HEX + _START_HEX + _LIMIT_HEX + 2  # + ≥1 domain byte
)


def clamp_page_size(n: int | None) -> int:
    """Bound an operator-supplied page size to a sane range (default 50)."""
    if n is None:
        return DEFAULT_PAGE_SIZE
    return max(MIN_PAGE_SIZE, min(n, MAX_PAGE_SIZE))


def encode_file_token(
    table_token: str, column_id: int, domain: str, start: int, limit: int
) -> str:
    """Encode a per-domain, per-page file token using only letters and digits.

    Positional, no delimiter, table token first: the (already-hex) table token
    + the column id + the page start offset + the page size (each fixed-width
    hex) + the domain's UTF-8 bytes as hex. Lowercase hex throughout —
    alphanumeric for any domain, with no ``.csv``.
    """
    return (
        table_token
        + format(column_id, f"0{_COL_HEX}x")
        + format(start, f"0{_START_HEX}x")
        + format(limit, f"0{_LIMIT_HEX}x")
        + domain.encode().hex()
    )


def decode_file_token(
    token: str,
) -> tuple[str, int, str, int | None, int | None] | None:
    """Return (table_token, column_id, domain, start, limit) for a composite token.

    ``start``/``limit`` describe the page for the current positional scheme, or
    are both ``None`` for the legacy ``~`` form (which addressed a whole domain,
    unpaged). A bare 32-char table token (too short to be composite) yields
    None, so the caller serves the whole table.
    """
    if _SEP in token:
        return _decode_legacy(token)
    if len(token) < _MIN_COMPOSITE or len(token) % 2:
        return None
    pos = _TT_LEN
    table_token = token[:pos]
    col_hex = token[pos : pos + _COL_HEX]
    pos += _COL_HEX
    start_hex = token[pos : pos + _START_HEX]
    pos += _START_HEX
    limit_hex = token[pos : pos + _LIMIT_HEX]
    pos += _LIMIT_HEX
    dom_hex = token[pos:]
    try:
        column_id = int(col_hex, 16)
        start = int(start_hex, 16)
        limit = int(limit_hex, 16)
        domain = bytes.fromhex(dom_hex).decode()
    except ValueError:
        return None
    return table_token, column_id, domain, start, limit


def _decode_legacy(
    token: str,
) -> tuple[str, int, str, int | None, int | None] | None:
    """Decode the old ``<table_token>~<col_id>~<urlsafe_b64(domain)>`` form."""
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
    return table_token, column_id, domain, None, None


async def column_value_counts(
    db: AsyncSession, table_id: int, column_id: int
) -> list[tuple[str, int]]:
    """Distinct non-empty values of a column with their row counts.

    Order-preserving (first appearance). Values are stripped so they match the
    domain encoded into per-domain tokens. The count is the domain's ``total``
    row count, from which the page set is derived.
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


async def ordered_row_ids_for_domain(
    db: AsyncSession, table_id: int, column_id: int, domain: str
) -> list[int]:
    """Ids of rows whose ``column_id`` cell (stripped) equals ``domain``.

    Ordered by (position, id) so that slicing by a page offset is deterministic
    and consistent with ``column_value_counts`` (same predicate + order).
    """
    pairs = (
        await db.execute(
            select(BulkTableCell.row_id, BulkTableCell.value)
            .join(BulkTableRow, BulkTableCell.row_id == BulkTableRow.id)
            .where(
                BulkTableRow.table_id == table_id,
                BulkTableCell.column_id == column_id,
            )
            .order_by(BulkTableRow.position, BulkTableRow.id)
        )
    ).all()
    return [rid for rid, val in pairs if (val or "").strip() == domain]


async def count_append_rows(db: AsyncSession, table: BulkTable) -> int:
    """Rows whose INCLUDED ``mode`` column holds "append" (case-insensitive).

    Autotool reads ``mode=append`` as "add the Content to whatever the WP page
    already has", so these rows duplicate content on a re-send. Respects the
    table's Autotool column selection — an unchecked ``mode`` column never
    reaches the CSV, so it can't append. ``table`` must be loaded with
    ``columns``. Single source of truth for both the send-preview count and the
    create-run acknowledgement gate.
    """
    selected = (
        None if table.autotool_column_ids is None else set(table.autotool_column_ids)
    )
    mode_col = next(
        (
            c
            for c in table.columns
            if c.name.strip().lower() == "mode"
            and (selected is None or c.id in selected)
        ),
        None,
    )
    if mode_col is None:
        return 0
    return sum(
        cnt
        for value, cnt in await column_value_counts(db, table.id, mode_col.id)
        if value.strip().lower() == "append"
    )
