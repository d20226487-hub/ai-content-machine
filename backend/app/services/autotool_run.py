"""Autotool send runs — background firing of the per-domain-page ImportPosts
POSTs, with a progress page.

A run is created from a shared table (validating target/key/site-column/domains
exactly like the old sync send), fanned out into one ``AutotoolRunItem`` per
(domain, page), then a Celery worker fires each POST and bumps the run counters.
The run finalises (``done``) when ``sent + failed + skipped >= total``.

Controls: Cancel (queued items → skipped; run → cancelled) and Retry-failed
(failed items → queued; run → running again on the SAME run).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.core.ssrf import SafeAsyncTransport, UnsafeUrlError, validate_public_url
from app.db.models import AppSetting, AutotoolRun, AutotoolRunItem, BulkTable
from app.schemas.autotool import (
    AutotoolRunDetail,
    AutotoolRunItemRead,
    AutotoolRunRead,
    AutotoolRunsPage,
)
from app.services.autotool_config import CONFIG_KEY, _detect_site_column
from app.services.autotool_files import (
    clamp_page_size,
    column_value_counts,
    encode_file_token,
)

_SEND_TIMEOUT_S = 20.0
_RESPONSE_SNIPPET = 500
_MAX_RUN_ITEMS = 5000  # runaway guard; a run beyond this should be split
_BUMP_FIELDS = {"sent", "failed"}


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")


# ----- read views -----


def _run_to_read(run: AutotoolRun) -> AutotoolRunRead:
    return AutotoolRunRead(
        id=run.id,
        table_id=run.table_id,
        table_name=run.table_name,
        target_url=run.target_url,
        page_size=run.page_size,
        external_id=run.external_id,
        status=run.status,
        total=run.total,
        sent=run.sent,
        failed=run.failed,
        skipped=run.skipped,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _item_to_read(it: AutotoolRunItem) -> AutotoolRunItemRead:
    return AutotoolRunItemRead(
        id=it.id,
        site=it.site,
        start=it.start,
        total=it.total,
        status=it.status,
        status_code=it.status_code,
        detail=it.detail,
        response_snippet=it.response_snippet,
        elapsed_ms=it.elapsed_ms,
        created_at=it.created_at,
    )


async def list_runs(db: AsyncSession, page: int, page_size: int) -> AutotoolRunsPage:
    total = (
        await db.execute(select(func.count()).select_from(AutotoolRun))
    ).scalar_one()
    runs = (
        (
            await db.execute(
                select(AutotoolRun)
                .order_by(AutotoolRun.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return AutotoolRunsPage(
        items=[_run_to_read(r) for r in runs],
        total=int(total),
        page=page,
        page_size=page_size,
    )


async def get_run_detail(
    db: AsyncSession, run_id: int, page: int, page_size: int
) -> AutotoolRunDetail:
    run = await db.get(AutotoolRun, run_id)
    if run is None:
        raise _not_found()
    items_total = (
        await db.execute(
            select(func.count())
            .select_from(AutotoolRunItem)
            .where(AutotoolRunItem.run_id == run_id)
        )
    ).scalar_one()
    items = (
        (
            await db.execute(
                select(AutotoolRunItem)
                .where(AutotoolRunItem.run_id == run_id)
                .order_by(AutotoolRunItem.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    base = _run_to_read(run)
    return AutotoolRunDetail(
        **base.model_dump(),
        site_column_id=run.site_column_id,
        error=run.error,
        items=[_item_to_read(i) for i in items],
        items_total=int(items_total),
        items_page=page,
        items_page_size=page_size,
    )


# ----- create -----


async def create_run(
    db: AsyncSession,
    table: BulkTable,
    site_column_id: int | None,
    page_size: int | None,
    user_id: int | None,
) -> AutotoolRun:
    """Validate config + build the page items, insert a queued run. ``table``
    must be loaded with its columns. The caller enqueues the seed task."""
    page_size = clamp_page_size(page_size)

    row = await db.get(AppSetting, CONFIG_KEY)
    raw = row.value if row and isinstance(row.value, dict) else {}
    target = raw.get("target_url")
    if not target:
        raise _bad_request("Set the Autotool target URL first.")
    if not raw.get("api_key_encrypted"):
        raise _bad_request("Set the Autotool API key first.")
    try:
        validate_public_url(target)
    except UnsafeUrlError as e:
        raise _bad_request(f"Target URL rejected: {e}")

    columns = list(table.columns)
    valid_ids = {c.id for c in columns}
    chosen = (
        site_column_id
        if site_column_id in valid_ids
        else _detect_site_column(columns)
    )
    if chosen is None or not table.autotool_token:
        raise _bad_request(
            "No site column selected — pick the column that holds the target sites."
        )
    counts = await column_value_counts(db, table.id, chosen)
    if not counts:
        raise _bad_request("No domains to send.")
    pages = [
        (domain, start, total)
        for domain, total in counts
        for start in range(0, total, page_size)
    ]
    if len(pages) > _MAX_RUN_ITEMS:
        raise _bad_request(
            f"Too many pages ({len(pages)}) for one run (max {_MAX_RUN_ITEMS}). "
            f"Use a larger page size or split the table."
        )

    run = AutotoolRun(
        table_id=table.id,
        table_name=table.name,
        target_url=target,
        site_column_id=chosen,
        page_size=page_size,
        status="queued",
        total=len(pages),
        created_by_id=user_id,
    )
    db.add(run)
    await db.flush()
    for domain, start, total in pages:
        token = encode_file_token(table.autotool_token, chosen, domain, start, page_size)
        db.add(
            AutotoolRunItem(
                run_id=run.id,
                site=domain,
                start=start,
                total=total,
                file_token=token,
                status="queued",
            )
        )
    await db.commit()
    await db.refresh(run)
    return run


# ----- run lifecycle (called by Celery) -----


async def start_run(db: AsyncSession, run_id: int) -> list[int]:
    """Flip a queued/running run to 'running' and return the item ids to enqueue.

    Leader-first: until the proxy id is known (``external_id`` is None) only the
    FIRST queued item is returned — it sends the first request, captures the id,
    then the rest fan out (re-seed) with that id. Once the id is set, all queued
    items are returned. Returns [] for terminal runs (or finalises a zero-item
    run)."""
    run = await db.get(AutotoolRun, run_id)
    if run is None or run.status in ("cancelled", "done", "failed"):
        return []
    if run.status == "queued" and run.started_at is None:
        run.started_at = datetime.now(timezone.utc)
    run.status = "running"
    await db.commit()

    if run.total == 0:
        run.status = "done"
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return []

    ids = (
        (
            await db.execute(
                select(AutotoolRunItem.id)
                .where(
                    AutotoolRunItem.run_id == run_id,
                    AutotoolRunItem.status == "queued",
                )
                .order_by(AutotoolRunItem.id.asc())
            )
        )
        .scalars()
        .all()
    )
    if not ids:
        return []
    # No id yet → send only the leader; it fans out the rest once it has the id.
    return [ids[0]] if run.external_id is None else list(ids)


async def _bump(db: AsyncSession, *, run_id: int, field: str) -> None:
    """Atomically increment sent/failed and finalise when the total is reached."""
    if field not in _BUMP_FIELDS:
        raise ValueError(f"_bump: field must be one of {_BUMP_FIELDS}, got {field!r}")
    await db.execute(
        text(f"UPDATE autotool_runs SET {field} = {field} + 1 WHERE id = :id"),
        {"id": run_id},
    )
    await db.execute(
        text(
            "UPDATE autotool_runs "
            "SET status = 'done', finished_at = now() "
            "WHERE id = :id AND status = 'running' "
            "AND sent + failed + skipped >= total AND total > 0"
        ),
        {"id": run_id},
    )
    await db.commit()


async def send_one_item(db: AsyncSession, run_id: int, item_id: int) -> str:
    """Fire one item's ImportPosts POST and record the outcome.

    The body is just ``{file}`` — ACM does the row-splitting, so the proxy
    doesn't need start/count/total. The leader (``run.external_id`` is None)
    sends the first request, captures the proxy ``id`` from its response, stores
    it, and signals a fan-out; every follower adds ``data.id`` so the proxy
    groups them into one import job. Idempotent via a guarded 'queued'->'sending'
    claim."""
    run = await db.get(AutotoolRun, run_id)
    if run is None or run.status in ("cancelled", "done", "failed"):
        return "run_terminal"

    now = datetime.now(timezone.utc)
    claim = await db.execute(
        update(AutotoolRunItem)
        .where(AutotoolRunItem.id == item_id, AutotoolRunItem.status == "queued")
        .values(status="sending", updated_at=now)
    )
    await db.commit()
    if (claim.rowcount or 0) != 1:
        return "not_queued"

    item = await db.get(AutotoolRunItem, item_id)
    is_leader = run.external_id is None
    has_followers = run.total > 1

    data: dict[str, Any] = {"file": item.file_token}
    if not is_leader:
        data["id"] = run.external_id
    body = {"sites": [item.site], "data": data}
    api_key = await _read_api_key(db)
    target = run.target_url
    headers = {"Content-Type": "application/json", "X-Api-Key": api_key or ""}

    status_code: int | None = None
    snippet: str | None = None
    elapsed: int | None = None
    captured_id: Any | None = None
    err: str | None = None

    if not api_key:
        err = "No API key configured."
    else:
        try:
            validate_public_url(target)
        except UnsafeUrlError as e:
            err = f"Target URL rejected: {e}"
        else:
            t0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(
                    transport=SafeAsyncTransport(),
                    timeout=_SEND_TIMEOUT_S,
                    follow_redirects=True,
                ) as client:
                    resp = await client.post(target, json=body, headers=headers)
            except (UnsafeUrlError, httpx.HTTPError) as e:
                err = f"{type(e).__name__}: {e}"[:200]
            else:
                elapsed = int((time.perf_counter() - t0) * 1000)
                status_code = resp.status_code
                snippet = (resp.text or "")[:_RESPONSE_SNIPPET]
                if is_leader:
                    captured_id = _extract_id(resp)

    http_ok = status_code is not None and 200 <= status_code < 300
    # The leader must also yield an id when there are followers to group under it.
    needs_id = is_leader and has_followers
    ok = http_ok and (captured_id is not None or not needs_id)
    if ok:
        detail = "Accepted"
    elif not http_ok:
        detail = err or (f"HTTP {status_code}" if status_code is not None else "Send failed")
    else:
        detail = "Autotool returned no id for the first request"

    item.status = "sent" if ok else "failed"
    item.detail = detail
    item.status_code = status_code
    item.response_snippet = snippet
    item.elapsed_ms = elapsed
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await _bump(db, run_id=run_id, field="sent" if ok else "failed")

    if is_leader and captured_id is not None:
        leader_run = await db.get(AutotoolRun, run_id)
        if leader_run is not None and leader_run.external_id is None:
            leader_run.external_id = captured_id
            await db.commit()
        return "fanout"
    if needs_id and captured_id is None:
        await _fail_run(
            db,
            run_id,
            "Autotool returned no id for the first request, so the remaining "
            "requests can't be grouped under it.",
        )
        return "no_id"
    return item.status


def _extract_id(resp: httpx.Response) -> Any | None:
    """Pull the import id from a response body (e.g. {..., "id": 178}); None if
    the body isn't JSON or has no ``id``."""
    try:
        data = resp.json()
    except Exception:
        return None
    return data.get("id") if isinstance(data, dict) else None


async def _fail_run(db: AsyncSession, run_id: int, error: str) -> None:
    """Terminate a run as 'failed' (e.g. the leader yielded no id)."""
    await db.execute(
        text(
            "UPDATE autotool_runs SET status='failed', finished_at=now(), "
            "error=:e WHERE id=:id AND status IN ('queued','running')"
        ),
        {"e": error[:1000], "id": run_id},
    )
    await db.commit()


async def _read_api_key(db: AsyncSession) -> str | None:
    row = await db.get(AppSetting, CONFIG_KEY)
    raw = row.value if row and isinstance(row.value, dict) else {}
    enc = raw.get("api_key_encrypted")
    if not enc:
        return None
    try:
        return decrypt(enc)
    except Exception:
        return None


# ----- controls -----


async def cancel_run(db: AsyncSession, run_id: int) -> AutotoolRunDetail:
    run = await db.get(AutotoolRun, run_id)
    if run is None:
        raise _not_found()
    if run.status in ("queued", "running"):
        now = datetime.now(timezone.utc)
        res = await db.execute(
            update(AutotoolRunItem)
            .where(
                AutotoolRunItem.run_id == run_id,
                AutotoolRunItem.status == "queued",
            )
            .values(status="skipped", updated_at=now)
        )
        run.skipped = (run.skipped or 0) + (res.rowcount or 0)
        run.status = "cancelled"
        run.finished_at = now
        await db.commit()
    return await get_run_detail(db, run_id, 1, 50)


async def retry_failed(db: AsyncSession, run_id: int) -> list[int]:
    """Reset failed items to 'queued' on the SAME run and re-arm it. Returns the
    requeued item ids for the caller to enqueue (via the seed task)."""
    run = await db.get(AutotoolRun, run_id)
    if run is None:
        raise _not_found()
    if run.status not in ("done", "failed", "cancelled"):
        raise _bad_request("Run is still in progress.")
    failed_ids = (
        (
            await db.execute(
                select(AutotoolRunItem.id).where(
                    AutotoolRunItem.run_id == run_id,
                    AutotoolRunItem.status == "failed",
                )
            )
        )
        .scalars()
        .all()
    )
    if not failed_ids:
        raise _bad_request("No failed items to retry.")
    now = datetime.now(timezone.utc)
    await db.execute(
        update(AutotoolRunItem)
        .where(
            AutotoolRunItem.run_id == run_id,
            AutotoolRunItem.status == "failed",
        )
        .values(
            status="queued",
            status_code=None,
            detail=None,
            response_snippet=None,
            elapsed_ms=None,
            updated_at=now,
        )
    )
    run.failed = max(0, run.failed - len(failed_ids))
    run.status = "running"
    run.finished_at = None
    await db.commit()
    return list(failed_ids)
