"""Schemas for the backup configuration + run history.

The S3 secret-access-key is encrypted at rest in `app_settings.value`. The
read-side schema returns a placeholder `***` when a secret is set so the
admin UI can show "configured / not configured" without leaking the value.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# How long to keep dump files locally / in S3 (days).
DEFAULT_LOCAL_RETENTION_DAYS = 14
DEFAULT_S3_RETENTION_DAYS = 30
# UTC hour-of-day for the scheduled run (0-23).
DEFAULT_SCHEDULE_HOUR_UTC = 3


class BackupConfigRead(BaseModel):
    # --- schedule ---
    schedule_enabled: bool = True
    schedule_hour_utc: int = DEFAULT_SCHEDULE_HOUR_UTC

    # --- destination ---
    s3_enabled: bool = False
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    # `True` if a secret access key is on file. The actual value is never
    # returned. Replace by sending a non-empty `s3_secret_access_key` on PUT.
    s3_secret_access_key_configured: bool = False
    s3_prefix: str = "acm/"

    # --- retention ---
    local_retention_days: int = DEFAULT_LOCAL_RETENTION_DAYS
    s3_retention_days: int = DEFAULT_S3_RETENTION_DAYS


class BackupConfigUpdate(BaseModel):
    schedule_enabled: bool | None = None
    schedule_hour_utc: int | None = Field(default=None, ge=0, le=23)

    s3_enabled: bool | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    # Empty string clears the stored key. None / omitted leaves it unchanged.
    s3_secret_access_key: str | None = None
    s3_prefix: str | None = None
    local_retention_days: int | None = Field(default=None, ge=1, le=365)
    s3_retention_days: int | None = Field(default=None, ge=1, le=3650)


class BackupTestResult(BaseModel):
    ok: bool
    message: str


class BackupRunRead(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    filename: str | None
    size_bytes: int | None
    local_path: str | None
    s3_key: str | None
    trigger: str
    error: str | None

    class Config:
        from_attributes = True
