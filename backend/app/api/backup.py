"""Admin endpoints for the backup system.

Routes (all admin-only):
  GET    /backup/config   — read current config (secrets masked)
  PUT    /backup/config   — update config; pass empty string to clear secret
  POST   /backup/test     — try a write+delete against the configured S3
  POST   /backup/run      — trigger a backup now (returns the queued job id)
  GET    /backup/runs     — list recent runs (most recent first)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.models import User
from app.db.session import get_db
from app.schemas.backup import (
    BackupConfigRead,
    BackupConfigUpdate,
    BackupRunRead,
    BackupTestResult,
)
from app.services.backup import (
    _read_raw_config,
    list_runs,
    read_config,
    test_s3,
    update_config,
)

router = APIRouter(
    prefix="/backup",
    tags=["backup"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("/config", response_model=BackupConfigRead)
async def get_config(db: AsyncSession = Depends(get_db)) -> BackupConfigRead:
    return await read_config(db)


@router.put("/config", response_model=BackupConfigRead)
async def put_config(
    payload: BackupConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BackupConfigRead:
    return await update_config(db, payload, user_id=user.id)


@router.post("/test", response_model=BackupTestResult)
async def test_connection(db: AsyncSession = Depends(get_db)) -> BackupTestResult:
    raw = await _read_raw_config(db)
    ok, message = await test_s3(raw)
    return BackupTestResult(ok=ok, message=message)


@router.post("/run", status_code=202)
async def run_now() -> dict:
    """Enqueue a backup task. Returns the task id; the result lands in
    /backup/runs once the worker finishes (poll every few seconds)."""
    # Imported lazily so the api process never imports celery's worker bits.
    from app.tasks.backup import run_backup_task

    result = run_backup_task.delay("manual")
    return {"task_id": result.id}


@router.get("/runs", response_model=list[BackupRunRead])
async def list_recent_runs(
    db: AsyncSession = Depends(get_db),
    limit: int = 30,
) -> list[BackupRunRead]:
    rows = await list_runs(db, limit=limit)
    return [BackupRunRead.model_validate(r) for r in rows]
