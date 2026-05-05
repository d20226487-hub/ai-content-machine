"""Domains CRUD + test connection + bulk CSV import.

Access: admin or manager. (Same as Users.)
"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import base64

import httpx

from app.api.deps import get_current_user, require_role
from app.cms.registry import UnsupportedCms, get_cms_client
from app.core.crypto import decrypt, encrypt
from app.core.ssrf import SafeAsyncTransport, UnsafeUrlError, validate_public_url
from app.db.models import Domain, User
from app.db.session import get_db
from app.services.media_cache import clear_for_domain, count_for_domain
from app.schemas.domain import (
    CsvImportResult,
    DomainCreate,
    DomainRead,
    DomainUpdate,
    TestConnectionResult,
    normalize_publish_config,
)

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
            "created_by_id": d.created_by_id,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        }
    )


@router.get("", response_model=list[DomainRead])
async def list_domains(db: AsyncSession = Depends(get_db)) -> list[DomainRead]:
    rows = (
        await db.execute(select(Domain).order_by(Domain.id))
    ).scalars().all()
    return [_to_read(d) for d in rows]


@router.post("", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
async def create_domain(
    payload: DomainCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> DomainRead:
    _validate_payload(payload.cms_type, payload.auth_type, payload.custom_config)

    domain = Domain(
        name=payload.name,
        base_url=payload.base_url,
        cms_type=payload.cms_type,
        auth_type=payload.auth_type,
        languages=payload.languages,
        multilingual_plugin=payload.multilingual_plugin,
        custom_config=payload.custom_config.model_dump() if payload.custom_config else None,
        publish_config=payload.publish_config.model_dump() if payload.publish_config else None,
        requests_per_minute=payload.requests_per_minute,
        max_concurrency=payload.max_concurrency,
        inter_request_delay_ms=payload.inter_request_delay_ms,
        retry_max_attempts=payload.retry_max_attempts,
        backoff_base_ms=payload.backoff_base_ms,
        backoff_jitter_ms=payload.backoff_jitter_ms,
        respect_retry_after=payload.respect_retry_after,
        created_by_id=actor.id,
    )
    if payload.credentials:
        domain.credentials_encrypted = encrypt(payload.credentials)

    db.add(domain)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A domain with base_url {payload.base_url!r} already exists",
        )
    await db.refresh(domain)
    return _to_read(domain)


@router.get("/{domain_id}", response_model=DomainRead)
async def get_domain(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> DomainRead:
    d = await db.get(Domain, domain_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_read(d)


@router.patch("/{domain_id}", response_model=DomainRead)
async def update_domain(
    domain_id: int,
    payload: DomainUpdate,
    db: AsyncSession = Depends(get_db),
) -> DomainRead:
    d = await db.get(Domain, domain_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")

    data = payload.model_dump(exclude_unset=True)

    # Validate effective cms_type/auth_type combination after the patch.
    next_cms = data.get("cms_type", d.cms_type)
    next_auth = data.get("auth_type", d.auth_type)
    next_custom = data.get("custom_config", d.custom_config)
    _validate_payload(next_cms, next_auth, next_custom if isinstance(next_custom, object) else None)

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
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="base_url conflict",
        )
    await db.refresh(d)
    return _to_read(d)


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_domain(
    domain_id: int, db: AsyncSession = Depends(get_db)
) -> Response:
    d = await db.get(Domain, domain_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(d)
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


def _validate_payload(
    cms_type: str, auth_type: str, custom_config: object
) -> None:
    if cms_type == "wordpress" and auth_type != "wp_app_password":
        raise HTTPException(
            status_code=400,
            detail="WordPress domains must use auth_type='wp_app_password'",
        )
    if cms_type == "custom" and auth_type not in ("bearer", "api_key_header"):
        raise HTTPException(
            status_code=400,
            detail="Custom domains must use auth_type='bearer' or 'api_key_header'",
        )
    if cms_type == "custom" and custom_config is None:
        raise HTTPException(
            status_code=400,
            detail="Custom domains require custom_config",
        )
