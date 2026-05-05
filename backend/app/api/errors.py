"""Error log viewer + frontend error reporter.

Read access: admin or manager.
Write access (delete, purge, retention update): admin only.
Frontend reporter: any authenticated user.
"""
import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Text, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.models import ErrorLog, User
from app.db.session import get_db
from app.schemas.error_log import (
    ErrorLogDetail,
    ErrorLogListItem,
    ErrorLogListResponse,
    FrontendErrorReport,
    PurgeResponse,
    RetentionResponse,
    RetentionUpdateRequest,
)
from app.services.error_log import (
    ALLOWED_RETENTION_DAYS,
    get_retention_days,
    log_error,
    purge_old,
    set_retention_days,
)

router = APIRouter(
    prefix="/errors",
    tags=["errors"],
    dependencies=[Depends(get_current_user)],
)


def _to_list_item(row: ErrorLog, user_email: str | None) -> ErrorLogListItem:
    return ErrorLogListItem(
        id=row.id,
        created_at=row.created_at,
        source=row.source,
        category=row.category,
        user_id=row.user_id,
        user_email=user_email,
        provider=row.provider,
        status_code=row.status_code,
        message=row.message,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
    )


@router.get("", response_model=ErrorLogListResponse)
async def list_errors(
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role("admin", "manager")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    source: str | None = None,
    category: str | None = None,
    provider: str | None = None,
    user_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
) -> ErrorLogListResponse:
    stmt = select(ErrorLog, User.email).join(
        User, User.id == ErrorLog.user_id, isouter=True
    )
    count_stmt = select(func.count(ErrorLog.id))

    conditions = []
    if source:
        conditions.append(ErrorLog.source == source)
    if category:
        conditions.append(ErrorLog.category == category)
    if provider:
        conditions.append(ErrorLog.provider == provider)
    if user_id is not None:
        conditions.append(ErrorLog.user_id == user_id)
    if since is not None:
        conditions.append(ErrorLog.created_at >= since)
    if until is not None:
        conditions.append(ErrorLog.created_at <= until)
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                ErrorLog.message.ilike(like),
                ErrorLog.context_json.cast(Text).ilike(like),
            )
        )

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(ErrorLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()
    items = [_to_list_item(r[0], r[1]) for r in rows]
    return ErrorLogListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/categories", response_model=dict[str, list[str]])
async def list_filter_options(
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role("admin", "manager")),
) -> dict[str, list[str]]:
    """Distinct values for filter dropdowns."""
    sources = (
        await db.execute(select(ErrorLog.source).distinct())
    ).scalars().all()
    categories = (
        await db.execute(select(ErrorLog.category).distinct())
    ).scalars().all()
    providers = (
        await db.execute(
            select(ErrorLog.provider)
            .where(ErrorLog.provider.is_not(None))
            .distinct()
        )
    ).scalars().all()
    return {
        "sources": sorted(s for s in sources if s),
        "categories": sorted(c for c in categories if c),
        "providers": sorted(p for p in providers if p),
    }


@router.get("/retention", response_model=RetentionResponse)
async def get_retention(
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role("admin", "manager")),
) -> RetentionResponse:
    days = await get_retention_days(db)
    return RetentionResponse(days=days, allowed=list(ALLOWED_RETENTION_DAYS))


@router.put("/retention", response_model=RetentionResponse)
async def update_retention(
    payload: RetentionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> RetentionResponse:
    if payload.days not in ALLOWED_RETENTION_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"days must be one of {list(ALLOWED_RETENTION_DAYS)}",
        )
    days = await set_retention_days(db, payload.days, updated_by_id=actor.id)
    return RetentionResponse(days=days, allowed=list(ALLOWED_RETENTION_DAYS))


@router.post("/purge", response_model=PurgeResponse)
async def manual_purge(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> PurgeResponse:
    deleted = await purge_old(db)
    return PurgeResponse(deleted=deleted)


EXPORT_ROW_CAP = 10_000

CSV_COLUMNS = [
    "id",
    "created_at",
    "source",
    "category",
    "user_email",
    "provider",
    "status_code",
    "message",
    "resource_type",
    "resource_id",
    "context_json",
    "stack_trace",
]


@router.get("/export.csv")
async def export_errors_csv(
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role("admin", "manager")),
    ids: str | None = Query(None, description="Comma-separated ID list. When set, filters are ignored."),
    source: str | None = None,
    category: str | None = None,
    provider: str | None = None,
    user_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
) -> StreamingResponse:
    """Stream filtered (or specifically-selected) error rows as CSV.

    - `ids=1,2,3` exports just those rows (other filters ignored).
    - Otherwise applies the same filters as `GET /errors` and returns up to
      `EXPORT_ROW_CAP` rows ordered by created_at desc.
    """
    stmt = select(ErrorLog, User.email).join(
        User, User.id == ErrorLog.user_id, isouter=True
    )

    if ids:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="ids must be comma-separated integers")
        if not id_list:
            raise HTTPException(status_code=400, detail="ids cannot be empty")
        if len(id_list) > EXPORT_ROW_CAP:
            raise HTTPException(
                status_code=400,
                detail=f"cannot export more than {EXPORT_ROW_CAP} ids at once",
            )
        stmt = stmt.where(ErrorLog.id.in_(id_list))
    else:
        if source:
            stmt = stmt.where(ErrorLog.source == source)
        if category:
            stmt = stmt.where(ErrorLog.category == category)
        if provider:
            stmt = stmt.where(ErrorLog.provider == provider)
        if user_id is not None:
            stmt = stmt.where(ErrorLog.user_id == user_id)
        if since is not None:
            stmt = stmt.where(ErrorLog.created_at >= since)
        if until is not None:
            stmt = stmt.where(ErrorLog.created_at <= until)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    ErrorLog.message.ilike(like),
                    ErrorLog.context_json.cast(Text).ilike(like),
                )
            )

    stmt = stmt.order_by(ErrorLog.created_at.desc()).limit(EXPORT_ROW_CAP)
    rows = (await db.execute(stmt)).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for err, user_email in rows:
        writer.writerow(
            [
                err.id,
                err.created_at.isoformat() if err.created_at else "",
                err.source or "",
                err.category or "",
                user_email or "",
                err.provider or "",
                err.status_code if err.status_code is not None else "",
                err.message or "",
                err.resource_type or "",
                err.resource_id or "",
                json.dumps(err.context_json or {}, ensure_ascii=False),
                err.stack_trace or "",
            ]
        )

    buffer.seek(0)
    filename = f"error_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{error_id}", response_model=ErrorLogDetail)
async def get_error(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role("admin", "manager")),
) -> ErrorLogDetail:
    row = (
        await db.execute(
            select(ErrorLog, User.email)
            .join(User, User.id == ErrorLog.user_id, isouter=True)
            .where(ErrorLog.id == error_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    err, user_email = row
    return ErrorLogDetail(
        id=err.id,
        created_at=err.created_at,
        source=err.source,
        category=err.category,
        user_id=err.user_id,
        user_email=user_email,
        provider=err.provider,
        status_code=err.status_code,
        message=err.message,
        resource_type=err.resource_type,
        resource_id=err.resource_id,
        context_json=err.context_json or {},
        stack_trace=err.stack_trace,
    )


@router.delete("/{error_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_error(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> None:
    row = await db.get(ErrorLog, error_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(row)
    await db.commit()


@router.post("/frontend", status_code=status.HTTP_204_NO_CONTENT)
async def report_frontend_error(
    payload: FrontendErrorReport,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Any authenticated user can report a JS error from the browser."""
    await log_error(
        db,
        source="frontend",
        category="frontend_js",
        message=payload.message,
        user_id=user.id,
        context={
            "url": payload.url,
            "user_agent": payload.user_agent or request.headers.get("user-agent"),
            "component": payload.component,
            "extra": payload.extra,
        },
        stack_trace=payload.stack,
    )
