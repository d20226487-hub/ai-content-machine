"""Backup service: pg_dump → gzipped file → optional S3 upload.

Storage model:
- `app_settings` row with key='backup_config' (jsonb) holds the operator-
  facing config: S3 endpoint, bucket, access key, prefix, retention.
- The S3 secret access key is encrypted with Fernet before being stored.
- Each invocation writes a row to `backup_runs` with timing and outcome.

Where the dumps live locally: `/var/backups/acm/` (mounted as a Docker
volume in compose). Filenames are `acm_YYYYMMDDTHHMMSSZ.sql.gz`.

Rotation:
- Local: keep the most recent N files (default 14), delete older.
- S3: list with the configured prefix and delete objects whose keys correspond
  to dumps older than M days. Naive but matches the daily cadence.

Errors are recorded on the `BackupRun` row AND copied into `error_logs` so
they show up in the admin error log too.
"""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.db.models import AppSetting, BackupRun
from app.schemas.backup import (
    DEFAULT_LOCAL_RETENTION_DAYS,
    DEFAULT_S3_RETENTION_DAYS,
    DEFAULT_SCHEDULE_HOUR_UTC,
    BackupConfigRead,
    BackupConfigUpdate,
)

log = logging.getLogger("acm.backup")

CONFIG_KEY = "backup_config"
LOCAL_DIR = Path("/var/backups/acm")
FILENAME_PREFIX = "acm_"
FILENAME_SUFFIX = ".sql.gz"


# --- config storage ------------------------------------------------------

async def _read_raw_config(db: AsyncSession) -> dict[str, Any]:
    row = await db.get(AppSetting, CONFIG_KEY)
    if row is None:
        return {}
    raw = row.value
    return dict(raw) if isinstance(raw, dict) else {}


def _public_view(raw: dict[str, Any]) -> BackupConfigRead:
    return BackupConfigRead(
        schedule_enabled=bool(raw.get("schedule_enabled", True)),
        schedule_hour_utc=int(
            raw.get("schedule_hour_utc", DEFAULT_SCHEDULE_HOUR_UTC)
        ),
        s3_enabled=bool(raw.get("s3_enabled")),
        s3_endpoint_url=raw.get("s3_endpoint_url"),
        s3_region=raw.get("s3_region"),
        s3_bucket=raw.get("s3_bucket"),
        s3_access_key_id=raw.get("s3_access_key_id"),
        s3_secret_access_key_configured=bool(raw.get("s3_secret_access_key_encrypted")),
        s3_prefix=raw.get("s3_prefix") or "acm/",
        local_retention_days=int(
            raw.get("local_retention_days", DEFAULT_LOCAL_RETENTION_DAYS)
        ),
        s3_retention_days=int(
            raw.get("s3_retention_days", DEFAULT_S3_RETENTION_DAYS)
        ),
    )


async def read_config(db: AsyncSession) -> BackupConfigRead:
    return _public_view(await _read_raw_config(db))


async def update_config(
    db: AsyncSession, payload: BackupConfigUpdate, user_id: int | None
) -> BackupConfigRead:
    raw = await _read_raw_config(db)
    data = payload.model_dump(exclude_unset=True)

    # Handle the secret separately so we never store it plaintext.
    # Empty string ⇒ explicit clear. Non-empty ⇒ replace. None / omitted ⇒ no change.
    if "s3_secret_access_key" in data:
        secret = data.pop("s3_secret_access_key")
        if secret == "":
            raw.pop("s3_secret_access_key_encrypted", None)
        elif secret:
            raw["s3_secret_access_key_encrypted"] = encrypt(secret)

    for key, value in data.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value

    stmt = (
        pg_insert(AppSetting)
        .values(key=CONFIG_KEY, value=raw, updated_by_id=user_id)
        .on_conflict_do_update(
            index_elements=["key"], set_={"value": raw, "updated_by_id": user_id}
        )
    )
    await db.execute(stmt)
    await db.commit()
    return _public_view(raw)


# --- S3 helpers ----------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _S3Creds:
    endpoint_url: str | None
    region: str | None
    bucket: str
    access_key_id: str
    secret_access_key: str
    prefix: str


def _resolve_s3(raw: dict[str, Any]) -> _S3Creds | None:
    """Returns S3 credentials when the config is complete enough to use,
    otherwise None. Uploads are silently skipped when None."""
    if not raw.get("s3_enabled"):
        return None
    bucket = raw.get("s3_bucket")
    access_key = raw.get("s3_access_key_id")
    encrypted_secret = raw.get("s3_secret_access_key_encrypted")
    if not (bucket and access_key and encrypted_secret):
        return None
    try:
        secret = decrypt(encrypted_secret)
    except Exception:
        log.exception("backup: S3 secret decrypt failed; skipping upload")
        return None
    return _S3Creds(
        endpoint_url=raw.get("s3_endpoint_url") or None,
        region=raw.get("s3_region") or None,
        bucket=bucket,
        access_key_id=access_key,
        secret_access_key=secret,
        prefix=(raw.get("s3_prefix") or "acm/").lstrip("/"),
    )


def _s3_client(creds: _S3Creds):  # type: ignore[no-untyped-def]
    # boto3 imported lazily so the module's import time doesn't pay for it.
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=creds.endpoint_url,
        region_name=creds.region,
        aws_access_key_id=creds.access_key_id,
        aws_secret_access_key=creds.secret_access_key,
    )


async def test_s3(raw: dict[str, Any]) -> tuple[bool, str]:
    """Try a minimal write+delete. Used by the admin "Test connection" button.

    The dict comes straight from `_read_raw_config`; we don't read it from
    the DB here because the admin may want to test values they haven't saved
    yet (a future refinement: accept overrides). For now operators save first,
    then test.
    """
    creds = _resolve_s3(raw)
    if creds is None:
        return (
            False,
            "Provide bucket + access key + secret access key, then save and try again.",
        )

    def _do() -> tuple[bool, str]:
        client = _s3_client(creds)
        key = creds.prefix + "_acm_test_marker.txt"
        body = b"acm-backup-test"
        try:
            client.put_object(Bucket=creds.bucket, Key=key, Body=body)
            client.delete_object(Bucket=creds.bucket, Key=key)
        except Exception as e:  # pragma: no cover - network/cred dependent
            return (False, f"S3 error: {e}")
        return (True, f"OK — wrote and deleted s3://{creds.bucket}/{key}")

    return await asyncio.to_thread(_do)


# --- backup execution ----------------------------------------------------

def _filename_for(now: datetime) -> str:
    return f"{FILENAME_PREFIX}{now.strftime('%Y%m%dT%H%M%SZ')}{FILENAME_SUFFIX}"


def _parse_dsn(dsn: str) -> dict[str, str]:
    """Pull host/port/user/password/db out of an asyncpg or sync DSN."""
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(dsn)
    return {
        "host": parsed.hostname or "db",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "db": (parsed.path or "/postgres").lstrip("/"),
    }


def _run_pg_dump(target_path: Path, dsn: str) -> int:
    """Run pg_dump → gzip → file. Returns the number of bytes written.

    Synchronous; called via asyncio.to_thread in the async wrapper.
    """
    parts = _parse_dsn(dsn)
    env = os.environ.copy()
    env["PGPASSWORD"] = parts["password"]
    cmd = [
        "pg_dump",
        "--host",
        parts["host"],
        "--port",
        parts["port"],
        "--username",
        parts["user"],
        "--dbname",
        parts["db"],
        "--no-owner",
        "--no-privileges",
        "--format=plain",
    ]
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with gzip.open(target_path, "wb") as gz:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
        assert proc.stdout is not None
        try:
            shutil.copyfileobj(proc.stdout, gz)  # type: ignore[arg-type]
        finally:
            proc.stdout.close()
        rc = proc.wait()
        if rc != 0:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            raise RuntimeError(f"pg_dump failed (rc={rc}): {stderr.strip()}")

    return target_path.stat().st_size


def _rotate_local(retention: int) -> None:
    if not LOCAL_DIR.exists():
        return
    files = sorted(
        (p for p in LOCAL_DIR.iterdir() if p.name.startswith(FILENAME_PREFIX)),
        key=lambda p: p.name,
        reverse=True,
    )
    for stale in files[retention:]:
        try:
            stale.unlink()
        except OSError:
            log.warning("backup: failed to delete stale local file %s", stale)


def _rotate_s3(creds: _S3Creds, retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    client = _s3_client(creds)
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=creds.bucket, Prefix=creds.prefix):
        for obj in page.get("Contents", []) or []:
            last_modified = obj.get("LastModified")
            if last_modified and last_modified < cutoff:
                client.delete_object(Bucket=creds.bucket, Key=obj["Key"])


async def perform_backup(
    db: AsyncSession,
    *,
    trigger: str,
) -> BackupRun:
    """Run pg_dump and (if configured) upload to S3. Returns the
    persisted BackupRun row."""
    raw = await _read_raw_config(db)
    settings_obj = get_settings()

    run = BackupRun(status="running", trigger=trigger)
    db.add(run)
    await db.commit()
    await db.refresh(run)

    started = time.monotonic()
    now = datetime.now(timezone.utc)
    filename = _filename_for(now)
    local_path = LOCAL_DIR / filename

    try:
        size = await asyncio.to_thread(
            _run_pg_dump, local_path, settings_obj.DATABASE_URL
        )

        s3_key: str | None = None
        creds = _resolve_s3(raw)
        if creds is not None:
            s3_key = creds.prefix + filename

            def _upload() -> None:
                client = _s3_client(creds)
                client.upload_file(str(local_path), creds.bucket, s3_key)

            await asyncio.to_thread(_upload)

        # Rotate AFTER the new file is durable, never before.
        local_retention = int(
            raw.get("local_retention_days", DEFAULT_LOCAL_RETENTION_DAYS)
        )
        await asyncio.to_thread(_rotate_local, local_retention)
        if creds is not None:
            s3_retention = int(
                raw.get("s3_retention_days", DEFAULT_S3_RETENTION_DAYS)
            )
            await asyncio.to_thread(_rotate_s3, creds, s3_retention)

        run.status = "ok"
        run.filename = filename
        run.size_bytes = size
        run.local_path = str(local_path)
        run.s3_key = s3_key
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        log.info(
            "backup ok",
            extra={
                "size_bytes": size,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "s3_key": s3_key,
            },
        )
    except Exception as e:
        run.status = "failed"
        run.error = str(e)[:4000]
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        log.exception("backup failed")
        # Best-effort cleanup of half-written file.
        try:
            if local_path.exists():
                local_path.unlink()
        except OSError:
            pass

    return run


async def list_runs(db: AsyncSession, limit: int = 30) -> list[BackupRun]:
    rows = (
        await db.execute(
            select(BackupRun).order_by(desc(BackupRun.started_at)).limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def should_run_scheduled_now(db: AsyncSession) -> bool:
    """Filter for the hourly beat task.

    Returns True iff:
      * scheduling is enabled in config, AND
      * the current UTC hour matches the configured hour, AND
      * we haven't already produced a successful (or in-flight) backup
        within the last 23 hours — that guard prevents a duplicate run
        from a one-off task replay or a clock blip.
    """
    raw = await _read_raw_config(db)
    if not bool(raw.get("schedule_enabled", True)):
        return False

    hour_target = int(raw.get("schedule_hour_utc", DEFAULT_SCHEDULE_HOUR_UTC))
    now = datetime.now(timezone.utc)
    if now.hour != hour_target:
        return False

    cutoff = now - timedelta(hours=23)
    recent = (
        await db.execute(
            select(BackupRun)
            .where(BackupRun.started_at >= cutoff)
            .where(BackupRun.status.in_(("ok", "running")))
            .limit(1)
        )
    ).scalar_one_or_none()
    return recent is None
