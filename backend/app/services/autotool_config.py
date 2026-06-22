"""Autotool connection config: storage + connection test.

Mirrors the backup-config pattern: one ``app_settings`` row (key
``autotool_config``) holds ``{target_url, api_key_encrypted}``. The API key is
Fernet-encrypted on write and never returned to callers.

The "Test" probes the configured ImportPosts endpoint with an EMPTY payload:
  * 401/403           → API key rejected
  * any other status  → reachable + key accepted (an empty body is a no-op for
                        ImportPosts, so this doesn't create a real task)
  * network error     → unreachable

The target URL is operator-supplied, so every outbound call goes through the
SSRF guard (validate_public_url + SafeAsyncTransport) — same protection the
domain Test uses.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.core.ssrf import SafeAsyncTransport, UnsafeUrlError, validate_public_url
from app.db.models import (
    AppSetting,
    BulkTable,
    BulkTableColumn,
    BulkTableRow,
)
from app.schemas.autotool import (
    AutotoolConfigRead,
    AutotoolConfigUpdate,
    AutotoolDomainRequest,
    AutotoolPostPreview,
    AutotoolTableItem,
    AutotoolTablesPage,
    AutotoolTestResult,
    ColumnRef,
)
from app.services.app_settings_cache import invalidate
from app.services.autotool_files import (
    clamp_page_size,
    column_value_counts,
    encode_file_token,
)

CONFIG_KEY = "autotool_config"
_TEST_TIMEOUT_S = 15.0
_API_KEY_MASK = "••••••••"
# Column-name hints used to auto-detect which column holds the target sites.
_SITE_EXACT = ("site", "sites", "domain", "domains", "url", "urls", "host", "hosts")
_SITE_CONTAINS = ("site", "domain", "url", "host")


async def _read_raw(db: AsyncSession) -> dict[str, Any]:
    row = await db.get(AppSetting, CONFIG_KEY)
    if row is None:
        return {}
    raw = row.value
    return dict(raw) if isinstance(raw, dict) else {}


def _public_view(raw: dict[str, Any]) -> AutotoolConfigRead:
    return AutotoolConfigRead(
        target_url=raw.get("target_url"),
        api_key_configured=bool(raw.get("api_key_encrypted")),
    )


async def read_config(db: AsyncSession) -> AutotoolConfigRead:
    return _public_view(await _read_raw(db))


async def update_config(
    db: AsyncSession, payload: AutotoolConfigUpdate, user_id: int | None
) -> AutotoolConfigRead:
    raw = await _read_raw(db)
    data = payload.model_dump(exclude_unset=True)

    # Secret handled separately so it's never stored plaintext.
    # ""  → clear, non-empty → replace, None/omitted → no change.
    if "api_key" in data:
        key = data.pop("api_key")
        if key == "":
            raw.pop("api_key_encrypted", None)
        elif key:
            raw["api_key_encrypted"] = encrypt(key)

    if "target_url" in data:
        url = data["target_url"]
        if url:
            raw["target_url"] = url.strip()
        else:
            raw.pop("target_url", None)

    stmt = (
        pg_insert(AppSetting)
        .values(key=CONFIG_KEY, value=raw, updated_by_id=user_id)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": raw, "updated_by_id": user_id},
        )
    )
    await db.execute(stmt)
    await db.commit()
    invalidate(CONFIG_KEY)
    return _public_view(raw)


async def test_connection(db: AsyncSession) -> AutotoolTestResult:
    raw = await _read_raw(db)
    target = raw.get("target_url")
    if not target:
        return AutotoolTestResult(ok=False, detail="No target URL configured.")
    enc = raw.get("api_key_encrypted")
    if not enc:
        return AutotoolTestResult(ok=False, detail="No API key configured.")
    try:
        api_key = decrypt(enc)
    except Exception:
        return AutotoolTestResult(
            ok=False, detail="Stored API key could not be decrypted."
        )

    try:
        validate_public_url(target)
    except UnsafeUrlError as e:
        return AutotoolTestResult(ok=False, detail=f"Target URL rejected: {e}")

    headers = {"Content-Type": "application/json", "X-Api-Key": api_key}
    # Empty payload: a no-op for ImportPosts but enough for the proxy to accept
    # or reject the X-Api-Key.
    body: dict[str, Any] = {"sites": [], "data": {}}

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            transport=SafeAsyncTransport(),
            timeout=_TEST_TIMEOUT_S,
            follow_redirects=True,
        ) as client:
            resp = await client.post(target, json=body, headers=headers)
    except UnsafeUrlError as e:
        return AutotoolTestResult(ok=False, detail=f"Target URL rejected: {e}")
    except httpx.HTTPError as e:
        return AutotoolTestResult(
            ok=False, detail=f"Could not reach Autotool: {e}"
        )
    elapsed = int((time.perf_counter() - start) * 1000)

    code = resp.status_code
    if code in (401, 403):
        return AutotoolTestResult(
            ok=False,
            status_code=code,
            detail="API key rejected.",
            elapsed_ms=elapsed,
        )
    return AutotoolTestResult(
        ok=True,
        status_code=code,
        detail="Reachable; API key accepted.",
        elapsed_ms=elapsed,
    )


# ----- shared tables + POST request preview -----


async def list_shared_tables(
    db: AsyncSession, page: int, page_size: int
) -> AutotoolTablesPage:
    """Paginated list of tables currently exposed to Autotool."""
    base = (
        BulkTable.autotool_enabled.is_(True),
        BulkTable.deleted_at.is_(None),
    )
    total = (
        await db.execute(select(func.count()).select_from(BulkTable).where(*base))
    ).scalar_one()

    tables = (
        (
            await db.execute(
                select(BulkTable)
                .where(*base)
                .order_by(BulkTable.updated_at.desc(), BulkTable.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    ids = [t.id for t in tables]

    col_counts: dict[int, int] = {}
    row_counts: dict[int, int] = {}
    if ids:
        col_counts = dict(
            (
                await db.execute(
                    select(BulkTableColumn.table_id, func.count())
                    .where(BulkTableColumn.table_id.in_(ids))
                    .group_by(BulkTableColumn.table_id)
                )
            ).all()
        )
        row_counts = dict(
            (
                await db.execute(
                    select(BulkTableRow.table_id, func.count())
                    .where(BulkTableRow.table_id.in_(ids))
                    .group_by(BulkTableRow.table_id)
                )
            ).all()
        )

    items = [
        AutotoolTableItem(
            id=t.id,
            name=t.name,
            autotool_token=t.autotool_token,
            csv_path=f"/autotool/{t.autotool_token}.csv" if t.autotool_token else None,
            row_count=row_counts.get(t.id, 0),
            column_count=col_counts.get(t.id, 0),
            updated_at=t.updated_at,
        )
        for t in tables
    ]
    return AutotoolTablesPage(
        items=items, total=int(total), page=page, page_size=page_size
    )


def _detect_site_column(columns: list[BulkTableColumn]) -> int | None:
    """Pick the column most likely to hold target sites by its name."""
    for hint in _SITE_EXACT:
        for c in columns:
            if c.name.strip().lower() == hint:
                return c.id
    for c in columns:
        n = c.name.strip().lower()
        if any(h in n for h in _SITE_CONTAINS):
            return c.id
    return None


async def build_post_preview(
    db: AsyncSession,
    table: BulkTable,
    site_column_id: int | None,
    page_size: int | None = None,
) -> AutotoolPostPreview:
    """Build the per-domain, per-page ImportPosts request preview for a table.

    ``table`` must be loaded with its columns. The table is split by the site
    column (auto-detected, or ``site_column_id`` if it's a valid column) into
    one file per distinct domain, then each domain into ``page_size``-row pages
    (operator-controlled, clamped to a sane range).
    """
    page_size = clamp_page_size(page_size)
    raw = await _read_raw(db)
    target = raw.get("target_url")
    api_key_configured = bool(raw.get("api_key_encrypted"))

    columns = list(table.columns)
    valid_ids = {c.id for c in columns}
    detected = _detect_site_column(columns)
    chosen = site_column_id if site_column_id in valid_ids else detected

    table_row_count = (
        await db.execute(
            select(func.count())
            .select_from(BulkTableRow)
            .where(BulkTableRow.table_id == table.id)
        )
    ).scalar_one()

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": _API_KEY_MASK if api_key_configured else "",
    }

    requests: list[AutotoolDomainRequest] = []
    total_matched = 0
    domain_count = 0
    if chosen is not None and table.autotool_token:
        for domain, total in await column_value_counts(db, table.id, chosen):
            domain_count += 1
            total_matched += total
            for start in range(0, total, page_size):
                file_token = encode_file_token(
                    table.autotool_token, chosen, domain, start, page_size
                )
                requests.append(
                    AutotoolDomainRequest(
                        site=domain,
                        file=file_token,
                        csv_path=f"/autotool/{file_token}.csv",
                        start=start,
                        total=total,
                        row_count=min(page_size, total - start),
                        body={
                            "sites": [domain],
                            "data": {
                                "file": file_token,
                                "start": start,
                                "count": page_size,
                                "total": total,
                            },
                        },
                    )
                )

    return AutotoolPostPreview(
        method="POST",
        url=target,
        headers=headers,
        columns=[ColumnRef(id=c.id, name=c.name) for c in columns],
        site_column_id=chosen,
        detected_site_column_id=detected,
        page_size=page_size,
        domain_count=domain_count,
        page_count=len(requests),
        total_rows_matched=total_matched,
        table_row_count=int(table_row_count),
        requests=requests,
        target_configured=bool(target),
        api_key_configured=api_key_configured,
    )
