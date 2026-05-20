"""Domains CRUD + test connection + bulk CSV import.

Access: admin or manager. (Same as Users.)
"""
from __future__ import annotations

import csv
import io
from typing import Any

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import base64

import httpx

from app.api.deps import get_current_user, require_role
from app.cms.registry import UnsupportedCms, get_cms_client
from app.core.crypto import decrypt, encrypt
from app.core.ssrf import SafeAsyncTransport, UnsafeUrlError, validate_public_url
from app.db.models import AppSetting, BulkPublishRun, Domain, DomainFolder, User
from app.db.session import get_db
from app.services.media_cache import clear_for_domain, count_for_domain
from app.schemas.domain import (
    CsvImportResult,
    DomainCreate,
    DomainPickerItem,
    DomainPickerResponse,
    DomainRead,
    DomainUpdate,
    TestConnectionResult,
    TrashBulkIds,
    _has_profiles,
    default_wp_profiles,
    normalize_publish_config,
)
from app.schemas.domain_folder import DomainBulkMove

router = APIRouter(
    prefix="/domains",
    tags=["domains"],
    dependencies=[Depends(require_role("admin", "manager"))],
)


def _to_read(d: Domain) -> DomainRead:
    return DomainRead.model_validate(
        {
            "id": d.id,
            "name": d.name,
            "base_url": d.base_url,
            "cms_type": d.cms_type,
            "auth_type": d.auth_type,
            "has_credentials": d.has_credentials,
            "languages": d.languages or [],
            "multilingual_plugin": d.multilingual_plugin,
            "custom_config": d.custom_config,
            "publish_config": normalize_publish_config(d.publish_config),
            "requests_per_minute": d.requests_per_minute,
            "max_concurrency": d.max_concurrency,
            "inter_request_delay_ms": d.inter_request_delay_ms,
            "retry_max_attempts": d.retry_max_attempts,
            "backoff_base_ms": d.backoff_base_ms,
            "backoff_jitter_ms": d.backoff_jitter_ms,
            "respect_retry_after": d.respect_retry_after,
            "folder_id": d.folder_id,
            "created_by_id": d.created_by_id,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
            "deleted_at": d.deleted_at,
        }
    )


# Sentinel: when the caller wants "only domains with no folder" (the
# implicit root), they send ``?folder_id=root`` instead of omitting the
# param. Omitting the param means "every folder" (the v1 behavior we
# preserve for callers that pre-date migration 0027).
_ROOT_SENTINEL = "root"


def _folder_clause(folder_id_param: str | None):
    """Translate ``?folder_id=N`` / ``=root`` / omit into a WHERE clause.

    Returns None when the param is omitted (no filter applied). Raises
    HTTPException(400) on a malformed value.

    Centralized so both the list endpoint and the picker apply the same
    semantics — a caller who passes ``folder_id=root`` to either gets
    the same set of rows.
    """
    if folder_id_param is None or folder_id_param == "":
        return None
    if folder_id_param == _ROOT_SENTINEL:
        return Domain.folder_id.is_(None)
    try:
        fid = int(folder_id_param)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=(
                f"folder_id must be an integer, 'root', or omitted "
                f"(got {folder_id_param!r})."
            ),
        )
    return Domain.folder_id == fid


@router.get("", response_model=list[DomainRead])
async def list_domains(
    folder_id: str | None = Query(
        None,
        description=(
            "Optional folder scope. Send a folder id to list domains in "
            "that folder; send the literal 'root' to list domains that "
            "sit in the implicit root (no folder); omit to list every "
            "domain regardless of folder placement."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> list[DomainRead]:
    """List active domains. Trashed rows are hidden — see /domains/trash.

    ``?folder_id=`` added in migration 0027. Backward-compatible: a
    caller that doesn't send the param still sees every active domain.
    """
    base = select(Domain).where(Domain.deleted_at.is_(None))
    clause = _folder_clause(folder_id)
    if clause is not None:
        base = base.where(clause)
    rows = (
        await db.execute(base.order_by(Domain.id))
    ).scalars().all()
    return [_to_read(d) for d in rows]


@router.get("/picker", response_model=DomainPickerResponse)
async def list_domains_picker(
    q: str | None = Query(
        None,
        max_length=200,
        description=(
            "Optional case-insensitive substring filter against name and "
            "base_url. Empty / whitespace = no filter."
        ),
    ),
    cms_type: str | None = Query(
        None,
        description="Optional filter — 'wordpress' or 'custom'.",
    ),
    folder_id: str | None = Query(
        None,
        description=(
            "Optional folder scope: a folder id, the literal 'root' "
            "(domains with no folder), or omit to ignore folder placement."
        ),
    ),
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(
        50,
        ge=1,
        le=200,
        description=(
            "Up to 200 per request. Default 50 is enough to render a "
            "scrollable dropdown without re-fetching for most use cases."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> DomainPickerResponse:
    """Lite, paginated, search-friendly endpoint for the modal pickers.

    Designed for the publish modals where users may have thousands of
    domains and an unfiltered ``GET /domains`` would be wasteful (each
    row carries a 1–2 KB ``publish_config`` blob that the picker
    doesn't need).

    Ordering: credentialled rows first (so the "first usable" auto-pick
    in the modal lands on something the user can actually publish to),
    then by name for stable scroll position.
    """
    base = select(Domain).where(Domain.deleted_at.is_(None))
    count_base = select(func.count(Domain.id)).where(Domain.deleted_at.is_(None))

    if cms_type:
        ct = cms_type.strip().lower()
        if ct not in ("wordpress", "custom"):
            raise HTTPException(
                status_code=400,
                detail=f"cms_type must be 'wordpress' or 'custom' (got {ct!r}).",
            )
        base = base.where(Domain.cms_type == ct)
        count_base = count_base.where(Domain.cms_type == ct)

    folder_clause = _folder_clause(folder_id)
    if folder_clause is not None:
        base = base.where(folder_clause)
        count_base = count_base.where(folder_clause)

    q_norm = (q or "").strip()
    if q_norm:
        # Substring match across both display surfaces — users sometimes
        # remember the domain by its URL ("the .uz one"), sometimes by
        # its display name. ILIKE handles the case-insensitive part;
        # `%` is escaped to avoid wildcard-injection (a `%` typed by
        # the user shouldn't match everything).
        like = "%" + q_norm.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
        base = base.where(
            Domain.name.ilike(like) | Domain.base_url.ilike(like)
        )
        count_base = count_base.where(
            Domain.name.ilike(like) | Domain.base_url.ilike(like)
        )

    total = int((await db.execute(count_base)).scalar_one())

    rows = (
        await db.execute(
            base.order_by(
                # has_credentials desc — coerced via case() because
                # SQLAlchemy can't sort on a Python @property. We sort
                # by the encrypted-blob's nullness instead, which is the
                # exact thing has_credentials checks under the hood.
                Domain.credentials_encrypted.is_(None).asc(),
                Domain.name.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = [
        DomainPickerItem(
            id=d.id,
            name=d.name,
            base_url=d.base_url,
            cms_type=d.cms_type,
            has_credentials=d.has_credentials,
            languages=d.languages or [],
        )
        for d in rows
    ]
    return DomainPickerResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


# ---------- trash ----------
#
# All endpoints under /domains/trash/* mirror the bulk_tables trash surface.
# The literal "trash" path segments come before the dynamic
# /domains/{domain_id} routes so FastAPI doesn't try to coerce "trash"/
# "count"/"retention" into int domain_ids.

_DOMAIN_TRASH_RETENTION_KEY = "domain_trash_retention_days"
_DOMAIN_TRASH_RETENTION_DEFAULT = 50
_DOMAIN_TRASH_RETENTION_MAX = 3650


@router.get("/trash/count", response_model=dict)
async def trash_count(db: AsyncSession = Depends(get_db)) -> dict:
    n = int(
        (
            await db.execute(
                select(func.count(Domain.id)).where(Domain.deleted_at.is_not(None))
            )
        ).scalar_one()
    )
    return {"count": n}


@router.get("/trash/retention", response_model=dict)
async def get_trash_retention(
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role("admin", "manager")),
) -> dict:
    row = (
        await db.execute(
            select(AppSetting.value).where(
                AppSetting.key == _DOMAIN_TRASH_RETENTION_KEY
            )
        )
    ).scalar_one_or_none()
    try:
        days = (
            max(0, int(row))
            if row is not None
            else _DOMAIN_TRASH_RETENTION_DEFAULT
        )
    except (TypeError, ValueError):
        days = _DOMAIN_TRASH_RETENTION_DEFAULT
    return {
        "days": days,
        "default": _DOMAIN_TRASH_RETENTION_DEFAULT,
        "max": _DOMAIN_TRASH_RETENTION_MAX,
    }


@router.put("/trash/retention", response_model=dict)
async def set_trash_retention(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> dict:
    raw = payload.get("days")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="`days` must be an integer (0 disables auto-empty).",
        )
    if days < 0 or days > _DOMAIN_TRASH_RETENTION_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"`days` must be between 0 and {_DOMAIN_TRASH_RETENTION_MAX}.",
        )
    existing = await db.get(AppSetting, _DOMAIN_TRASH_RETENTION_KEY)
    if existing is None:
        db.add(AppSetting(key=_DOMAIN_TRASH_RETENTION_KEY, value=days))
    else:
        existing.value = days
    await db.commit()
    try:
        from app.services.app_settings_cache import invalidate
        invalidate(_DOMAIN_TRASH_RETENTION_KEY)
    except Exception:
        pass
    return {
        "days": days,
        "default": _DOMAIN_TRASH_RETENTION_DEFAULT,
        "max": _DOMAIN_TRASH_RETENTION_MAX,
    }


@router.get("/trash", response_model=list[DomainRead])
async def list_trashed_domains(
    db: AsyncSession = Depends(get_db),
) -> list[DomainRead]:
    rows = (
        await db.execute(
            select(Domain)
            .where(Domain.deleted_at.is_not(None))
            .order_by(Domain.deleted_at.desc())
        )
    ).scalars().all()
    return [_to_read(d) for d in rows]


@router.get("/trash/{domain_id}", response_model=DomainRead)
async def preview_trashed_domain(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> DomainRead:
    """Read-only preview of a trashed domain. Active surfaces 404 it."""
    d = (
        await db.execute(
            select(Domain).where(
                Domain.id == domain_id, Domain.deleted_at.is_not(None)
            )
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_read(d)


@router.post("/{domain_id}/restore", response_model=DomainRead)
async def restore_domain(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> DomainRead:
    """Restore a trashed domain to the active set.

    The partial-unique indexes ``uq_domains_name_active`` /
    ``uq_domains_base_url_active`` skip trashed rows, so while the
    domain was in trash someone may have created a new active domain
    with the same name or base_url. Check that explicitly before
    flipping deleted_at — a clean 409 is better than the IntegrityError
    that would otherwise come out of the partial index when we commit.
    """
    d = (
        await db.execute(
            select(Domain).where(
                Domain.id == domain_id, Domain.deleted_at.is_not(None)
            )
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")

    clash = (
        await db.execute(
            select(Domain.id, Domain.name, Domain.base_url).where(
                Domain.deleted_at.is_(None),
                Domain.id != d.id,
                (Domain.name == d.name) | (Domain.base_url == d.base_url),
            )
        )
    ).first()
    if clash is not None:
        _, clash_name, clash_url = clash
        which = "name" if clash_name == d.name else "base_url"
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot restore: an active domain with the same {which} "
                f"already exists. Rename or trash the conflicting domain first."
            ),
        )

    d.deleted_at = None
    await db.commit()
    await db.refresh(d)
    return _to_read(d)


@router.delete(
    "/{domain_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def permanently_delete_domain(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> Response:
    """Hard-delete a trashed domain. Related publish_jobs.domain_id is
    set NULL via the existing FK (publish_jobs jobs survive, just lose
    the domain back-reference and render as '(deleted)' in history)."""
    d = (
        await db.execute(
            select(Domain).where(
                Domain.id == domain_id, Domain.deleted_at.is_not(None)
            )
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(d)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/trash", response_model=dict)
async def empty_trash(db: AsyncSession = Depends(get_db)) -> dict:
    rows = (
        await db.execute(
            select(Domain).where(Domain.deleted_at.is_not(None))
        )
    ).scalars().all()
    for d in rows:
        await db.delete(d)
    await db.commit()
    return {"deleted": len(rows)}


@router.post("/trash/bulk-restore", response_model=dict)
async def bulk_restore_domains(
    payload: TrashBulkIds, db: AsyncSession = Depends(get_db)
) -> dict:
    rows = (
        await db.execute(
            select(Domain).where(
                Domain.id.in_(payload.ids), Domain.deleted_at.is_not(None)
            )
        )
    ).scalars().all()
    for d in rows:
        d.deleted_at = None
    await db.commit()
    return {"restored": len(rows)}


@router.delete("/trash/bulk", response_model=dict)
async def bulk_permanent_delete_domains(
    payload: TrashBulkIds, db: AsyncSession = Depends(get_db)
) -> dict:
    rows = (
        await db.execute(
            select(Domain).where(
                Domain.id.in_(payload.ids), Domain.deleted_at.is_not(None)
            )
        )
    ).scalars().all()
    for d in rows:
        await db.delete(d)
    await db.commit()
    return {"deleted": len(rows)}


@router.post("/bulk-move", response_model=dict)
async def bulk_move_domains(
    payload: DomainBulkMove,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Move N active domains to a folder (or out of any folder).

    Used by the "Move to folder…" bulk action in the /publish/domains
    redesign. Trashed domains are silently skipped — only active rows
    can be moved (a trashed domain shouldn't suddenly hop into a folder
    behind the user's back).

    Body: ``{"domain_ids": [int, ...], "folder_id": int | null}``.
    Returns ``{"moved": <count>}`` so the UI can confirm.
    """
    if payload.folder_id is not None:
        await _require_folder_exists(db, payload.folder_id)

    rows = (
        await db.execute(
            select(Domain).where(
                Domain.id.in_(payload.domain_ids),
                Domain.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for d in rows:
        d.folder_id = payload.folder_id
    await db.commit()
    return {"moved": len(rows)}


@router.post("", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
async def create_domain(
    payload: DomainCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> DomainRead:
    _validate_payload(payload.cms_type, payload.auth_type, payload.custom_config)

    if payload.folder_id is not None:
        # Reject up front so the user gets a 400 instead of a vague IntegrityError
        # if they reference a folder that doesn't exist.
        await _require_folder_exists(db, payload.folder_id)

    pc_dump = payload.publish_config.model_dump() if payload.publish_config else None
    if payload.cms_type == "wordpress" and not _has_profiles(pc_dump):
        pc_dump = default_wp_profiles()

    domain = Domain(
        name=payload.name,
        base_url=payload.base_url,
        cms_type=payload.cms_type,
        auth_type=payload.auth_type,
        languages=payload.languages,
        multilingual_plugin=payload.multilingual_plugin,
        custom_config=payload.custom_config.model_dump() if payload.custom_config else None,
        publish_config=pc_dump,
        requests_per_minute=payload.requests_per_minute,
        max_concurrency=payload.max_concurrency,
        inter_request_delay_ms=payload.inter_request_delay_ms,
        retry_max_attempts=payload.retry_max_attempts,
        backoff_base_ms=payload.backoff_base_ms,
        backoff_jitter_ms=payload.backoff_jitter_ms,
        respect_retry_after=payload.respect_retry_after,
        folder_id=payload.folder_id,
        created_by_id=actor.id,
    )
    if payload.credentials:
        domain.credentials_encrypted = encrypt(payload.credentials)

    db.add(domain)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        # Distinguish which uniqueness was violated: domains.name (added in
        # 0017 for multi-mode lookup) or domains.base_url. Postgres surfaces
        # the constraint name; asyncpg surfaces it via the cause chain.
        cause_text = str(e.orig) if getattr(e, "orig", None) else str(e)
        if "uq_domains_name" in cause_text:
            detail = f"A domain named {payload.name!r} already exists. Pick a different name."
        else:
            detail = f"A domain with base_url {payload.base_url!r} already exists"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    await db.refresh(domain)
    return _to_read(domain)


async def _get_active_domain_or_404(
    db: AsyncSession, domain_id: int
) -> Domain:
    """Fetch a domain that hasn't been trashed. Active surfaces never
    see trashed rows — they have to go through /domains/trash/{id}."""
    d = (
        await db.execute(
            select(Domain).where(
                Domain.id == domain_id, Domain.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    return d


@router.get("/{domain_id}", response_model=DomainRead)
async def get_domain(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> DomainRead:
    d = await _get_active_domain_or_404(db, domain_id)
    return _to_read(d)


@router.patch("/{domain_id}", response_model=DomainRead)
async def update_domain(
    domain_id: int,
    payload: DomainUpdate,
    db: AsyncSession = Depends(get_db),
) -> DomainRead:
    d = await _get_active_domain_or_404(db, domain_id)

    data = payload.model_dump(exclude_unset=True)

    # Validate effective cms_type/auth_type combination after the patch.
    next_cms = data.get("cms_type", d.cms_type)
    next_auth = data.get("auth_type", d.auth_type)
    next_custom = data.get("custom_config", d.custom_config)
    _validate_payload(next_cms, next_auth, next_custom if isinstance(next_custom, object) else None)

    # folder_id may be null (moves to implicit root) — only validate
    # existence when the caller passes a non-null id.
    if "folder_id" in data and data["folder_id"] is not None:
        await _require_folder_exists(db, data["folder_id"])

    if "credentials" in data:
        raw = data.pop("credentials")
        if raw == "":
            d.credentials_encrypted = None
        elif raw is not None:
            d.credentials_encrypted = encrypt(raw)
        # raw is None → leave unchanged (no-op, matches providers PATCH semantics)

    if "custom_config" in data:
        cc = data.pop("custom_config")
        d.custom_config = cc.model_dump() if hasattr(cc, "model_dump") else cc

    if "publish_config" in data:
        pc = data.pop("publish_config")
        d.publish_config = pc.model_dump() if hasattr(pc, "model_dump") else pc

    for field, value in data.items():
        setattr(d, field, value)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        cause_text = str(e.orig) if getattr(e, "orig", None) else str(e)
        if "uq_domains_name" in cause_text:
            new_name = data.get("name", d.name)
            detail = f"A domain named {new_name!r} already exists. Pick a different name."
        else:
            detail = "base_url conflict"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    await db.refresh(d)
    return _to_read(d)


_ACTIVE_BULK_RUN_STATUSES = ("queued", "running", "paused")


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_domain(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> Response:
    """Move a domain to trash (soft-delete).

    Sets ``deleted_at = now()`` so the domain disappears from
    /publish/domains and from every publish picker. The credentials,
    publish profiles, rate-limit overrides, and media cache all survive
    — Restore brings them back intact.

    Refuses (409) when an in-flight bulk publish run targets this
    domain (queued / running / paused). Cancel the run first.
    """
    d = await _get_active_domain_or_404(db, domain_id)
    blocking_run_id = (
        await db.execute(
            select(BulkPublishRun.id)
            .where(
                BulkPublishRun.domain_id == d.id,
                BulkPublishRun.status.in_(_ACTIVE_BULK_RUN_STATUSES),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if blocking_run_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot trash this domain while bulk publish run "
                f"#{int(blocking_run_id)} is in flight against it. "
                f"Cancel the run first (/publish/runs/{int(blocking_run_id)})."
            ),
        )
    d.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{domain_id}/test", response_model=TestConnectionResult)
async def test_domain_connection(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> TestConnectionResult:
    d = await db.get(Domain, domain_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        client = get_cms_client(d)
    except UnsupportedCms as e:
        return TestConnectionResult(ok=False, status_code=None, detail=str(e))
    result = await client.test_connection()
    return TestConnectionResult(
        ok=result.ok,
        status_code=result.status_code,
        detail=result.detail,
        elapsed_ms=result.elapsed_ms,
    )


@router.get("/{domain_id}/wp-types", response_model=list[dict])
async def get_wp_types(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Discover post types from this WordPress site via GET /wp-json/wp/v2/types.

    Returns ``[{"slug": "posts", "name": "Posts"}, ...]``. Falls back to an
    empty list on any error so the form can offer a free-text input.
    """
    d = await db.get(Domain, domain_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    if d.cms_type != "wordpress":
        return []
    try:
        url = f"{d.base_url}/wp-json/wp/v2/types"
        validate_public_url(url)
        async with httpx.AsyncClient(
            timeout=15.0, transport=SafeAsyncTransport()
        ) as client:
            resp = await client.get(
                url,
                headers=_basic_auth_header(d.credentials_encrypted),
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, dict):
            return []
        # WP returns {"post": {...}, "page": {...}, "events": {...}}.
        # The "rest_base" field is the actual REST endpoint segment.
        out: list[dict] = []
        for key, info in data.items():
            if not isinstance(info, dict):
                continue
            slug = info.get("rest_base") or key
            name = info.get("name") or key
            out.append({"slug": str(slug), "name": str(name)})
        out.sort(key=lambda x: x["slug"])
        return out
    except (httpx.HTTPError, UnsafeUrlError):
        return []


@router.get("/{domain_id}/wp-taxonomies", response_model=list[dict])
async def get_wp_taxonomies(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Discover taxonomies from this WordPress site via GET /wp-json/wp/v2/taxonomies."""
    d = await db.get(Domain, domain_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    if d.cms_type != "wordpress":
        return []
    try:
        url = f"{d.base_url}/wp-json/wp/v2/taxonomies"
        validate_public_url(url)
        async with httpx.AsyncClient(
            timeout=15.0, transport=SafeAsyncTransport()
        ) as client:
            resp = await client.get(
                url,
                headers=_basic_auth_header(d.credentials_encrypted),
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, dict):
            return []
        out: list[dict] = []
        for key, info in data.items():
            if not isinstance(info, dict):
                continue
            slug = info.get("rest_base") or key
            name = info.get("name") or key
            out.append({"slug": str(slug), "name": str(name)})
        out.sort(key=lambda x: x["slug"])
        return out
    except (httpx.HTTPError, UnsafeUrlError):
        return []


@router.get("/{domain_id}/media-cache/count", response_model=dict)
async def media_cache_count(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    d = await db.get(Domain, domain_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {"count": await count_for_domain(db, domain_id)}


@router.delete(
    "/{domain_id}/media-cache",
    status_code=status.HTTP_200_OK,
)
async def clear_media_cache(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    d = await db.get(Domain, domain_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    deleted = await clear_for_domain(db, domain_id)
    return {"deleted": deleted}


def _basic_auth_header(credentials_encrypted: str | None) -> dict[str, str]:
    """Build a Basic-auth header from an encrypted WP Application Password.

    Some WP REST endpoints expose richer responses (e.g. private types) when
    authenticated. Returns an empty dict when no credentials are stored.
    """
    if not credentials_encrypted:
        return {}
    try:
        creds = decrypt(credentials_encrypted)
    except Exception:
        return {}
    token = base64.b64encode(creds.encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


@router.post("/import-csv", response_model=CsvImportResult)
async def import_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CsvImportResult:
    """Import domains from a CSV. Header row required. Columns:

    name, base_url, cms_type, auth_type, credentials, languages,
    multilingual_plugin

    languages may be a single value ("en") or a comma-separated list inside
    quotes ("en,de,fr"). multilingual_plugin defaults to 'none' if blank.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    required = {"name", "base_url", "cms_type", "auth_type"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=400,
            detail=f"Missing required CSV columns. Required: {sorted(required)}",
        )

    inserted = 0
    skipped = 0
    errors: list[dict[str, Any]] = []

    for row_index, row in enumerate(reader, start=2):  # row 1 is header
        try:
            languages_raw = (row.get("languages") or "").strip()
            languages = (
                [c.strip() for c in languages_raw.split(",") if c.strip()]
                if languages_raw
                else []
            )

            payload = DomainCreate(
                name=(row.get("name") or "").strip(),
                base_url=(row.get("base_url") or "").strip(),
                cms_type=(row.get("cms_type") or "").strip().lower(),
                auth_type=(row.get("auth_type") or "").strip().lower(),
                languages=languages,
                multilingual_plugin=(
                    row.get("multilingual_plugin") or "none"
                ).strip().lower() or "none",
                credentials=(row.get("credentials") or "").strip() or None,
            )
        except Exception as e:
            errors.append({"row": row_index, "detail": str(e)})
            skipped += 1
            continue

        try:
            _validate_payload(payload.cms_type, payload.auth_type, payload.custom_config)
        except HTTPException as e:
            errors.append({"row": row_index, "detail": str(e.detail)})
            skipped += 1
            continue

        domain = Domain(
            name=payload.name,
            base_url=payload.base_url,
            cms_type=payload.cms_type,
            auth_type=payload.auth_type,
            languages=payload.languages,
            multilingual_plugin=payload.multilingual_plugin,
            custom_config=None,
            publish_config=(
                default_wp_profiles() if payload.cms_type == "wordpress" else None
            ),
            created_by_id=actor.id,
        )
        if payload.credentials:
            domain.credentials_encrypted = encrypt(payload.credentials)
        db.add(domain)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            errors.append({"row": row_index, "detail": "base_url already exists"})
            skipped += 1
            continue
        inserted += 1

    return CsvImportResult(inserted=inserted, skipped=skipped, errors=errors)


@router.post("/import-json", response_model=CsvImportResult)
async def import_json(
    payload: list[dict[str, Any]],
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CsvImportResult:
    """Bulk-create domains from a JSON array.

    Same shape as the single-domain ``POST /domains`` endpoint, repeated
    per element. Unlike the CSV importer this DOES carry the full nested
    ``publish_config`` (profiles + their fields[]) and ``custom_config``,
    so you can stand up a fleet of multi-profile sites in one call.

    Per-row failures (validation, conflict) are collected into
    ``errors[]`` so a single bad row doesn't abort the rest of the batch
    — matches the CSV importer's semantics. The endpoint accepts
    ``list[dict]`` (not ``list[DomainCreate]``) on purpose: Pydantic at
    the request boundary would reject the entire batch on the first
    invalid row. We construct + validate each ``DomainCreate`` inside
    the loop instead, catching ``ValidationError`` to surface a per-row
    message.

    Response shape: ``CsvImportResult`` (same {inserted, skipped,
    errors[]} as the CSV path).
    """
    if not isinstance(payload, list) or not payload:
        raise HTTPException(
            status_code=400,
            detail="Body must be a non-empty JSON array of domain objects.",
        )
    if len(payload) > 500:
        raise HTTPException(
            status_code=400,
            detail="Import is capped at 500 domains per call. Split into chunks.",
        )

    from pydantic import ValidationError

    inserted = 0
    skipped = 0
    errors: list[dict[str, Any]] = []
    # `actor` is bound to the session. After the first per-row commit,
    # its attributes expire and the next access fires sync I/O under the
    # async session → MissingGreenlet. Cache the id locally so the loop
    # only reads a Python int from here on.
    actor_id = actor.id

    for idx, raw in enumerate(payload, start=1):
        if not isinstance(raw, dict):
            errors.append({"row": idx, "detail": "Row must be a JSON object."})
            skipped += 1
            continue
        try:
            item = DomainCreate.model_validate(raw)
        except ValidationError as e:
            # Flatten the first-line of each Pydantic error so users see
            # something actionable instead of the nested dump.
            messages = [
                f"{'.'.join(str(x) for x in err.get('loc', ()) ) or '?'}: {err.get('msg', '?')}"
                for err in e.errors()
            ]
            errors.append({"row": idx, "detail": "; ".join(messages)})
            skipped += 1
            continue
        try:
            _validate_payload(item.cms_type, item.auth_type, item.custom_config)
        except HTTPException as e:
            errors.append({"row": idx, "detail": str(e.detail)})
            skipped += 1
            continue

        pc_dump = item.publish_config.model_dump() if item.publish_config else None
        if item.cms_type == "wordpress" and not _has_profiles(pc_dump):
            pc_dump = default_wp_profiles()

        domain = Domain(
            name=item.name,
            base_url=item.base_url,
            cms_type=item.cms_type,
            auth_type=item.auth_type,
            languages=item.languages,
            multilingual_plugin=item.multilingual_plugin,
            custom_config=item.custom_config.model_dump() if item.custom_config else None,
            publish_config=pc_dump,
            requests_per_minute=item.requests_per_minute,
            max_concurrency=item.max_concurrency,
            inter_request_delay_ms=item.inter_request_delay_ms,
            retry_max_attempts=item.retry_max_attempts,
            backoff_base_ms=item.backoff_base_ms,
            backoff_jitter_ms=item.backoff_jitter_ms,
            respect_retry_after=item.respect_retry_after,
            created_by_id=actor_id,
        )
        if item.credentials:
            domain.credentials_encrypted = encrypt(item.credentials)

        db.add(domain)
        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            # Surface which uniqueness was violated, same as POST /domains.
            cause_text = str(e.orig) if getattr(e, "orig", None) else str(e)
            if "uq_domains_name_active" in cause_text or "uq_domains_name" in cause_text:
                detail = f"name {item.name!r} already in use by an active domain"
            elif "uq_domains_base_url_active" in cause_text or "uq_domains_base_url" in cause_text:
                detail = f"base_url {item.base_url!r} already in use by an active domain"
            else:
                detail = "uniqueness conflict"
            errors.append({"row": idx, "detail": detail})
            skipped += 1
            continue
        inserted += 1

    return CsvImportResult(inserted=inserted, skipped=skipped, errors=errors)


async def _require_folder_exists(db: AsyncSession, folder_id: int) -> None:
    """Raise 400 if ``folder_id`` doesn't refer to an existing DomainFolder.

    The PATCH and create endpoints validate at the application layer
    rather than letting Postgres raise IntegrityError, so the user gets
    a clean error string instead of "violates foreign key constraint
    \"domains_folder_id_fkey\"" — same UX rule as Prompts categories.
    """
    exists = (
        await db.execute(
            select(DomainFolder.id).where(DomainFolder.id == folder_id)
        )
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=400,
            detail=f"Folder #{folder_id} not found.",
        )


def _validate_payload(
    cms_type: str, auth_type: str, custom_config: object
) -> None:
    if cms_type == "wordpress" and auth_type != "wp_app_password":
        raise HTTPException(
            status_code=400,
            detail="WordPress domains must use auth_type='wp_app_password'",
        )
    if cms_type == "custom" and auth_type not in ("bearer", "api_key_header", "basic_auth"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Custom domains must use auth_type='bearer', 'api_key_header', "
                "or 'basic_auth'"
            ),
        )
    if cms_type == "custom" and custom_config is None:
        raise HTTPException(
            status_code=400,
            detail="Custom domains require custom_config",
        )
