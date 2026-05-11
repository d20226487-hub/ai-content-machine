import asyncio

from celery import Celery
from celery.schedules import crontab
from celery.signals import (
    setup_logging,
    task_failure,
    task_postrun,
    task_prerun,
)

from app.core.config import get_settings
from app.core.logging import configure_logging, set_request_id
from app.core.sentry import init_sentry

settings = get_settings()

# Sentry — no-op when SENTRY_DSN is unset. Initialized at module-import time
# so it covers tasks loaded later via `include`.
init_sentry("worker")

celery_app = Celery(
    "acm",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.example",
        "app.tasks.bulk_generation",
        "app.tasks.publish_bulk",
        "app.tasks.publish_single",
        "app.tasks.backup",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Beat fires hourly. The task body reads `app_settings.backup_config`
        # to decide whether THIS hour matches the user-configured time-of-day
        # and whether scheduling is enabled at all. This way changing the
        # schedule from the UI takes effect immediately — no worker restart.
        "hourly-backup-check": {
            "task": "backup.run",
            "schedule": crontab(minute=0),
            "args": ("scheduled",),
        },
    },
)


@setup_logging.connect
def _setup_celery_logging(*_args, **_kwargs) -> None:
    """Apply our structured logging config inside the worker.

    Celery installs its own logging by default; we replace it with the same
    formatter the api uses so logs from both stream consistently.
    """
    configure_logging(level=settings.LOG_LEVEL, fmt=settings.LOG_FORMAT)


@task_prerun.connect
def _bind_task_id(task_id=None, **_kwargs) -> None:
    """Bind the celery task_id as the correlation id for the duration of the
    task. Picked up by the same `request_id` field in our log formatter."""
    if task_id:
        set_request_id(str(task_id))


@task_postrun.connect
def _unbind_task_id(**_kwargs) -> None:
    set_request_id("")


@task_failure.connect
def _on_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **_kw,
) -> None:
    """Log every uncaught Celery task exception."""
    from app.services.error_log import log_error_standalone

    task_name = getattr(sender, "name", None) or "unknown"
    tb_text = str(einfo) if einfo is not None else None

    try:
        asyncio.run(
            log_error_standalone(
                source="worker",
                category="task_failure",
                message=f"{type(exception).__name__ if exception else 'Error'}: {exception}",
                context={
                    "task_name": task_name,
                    "task_id": str(task_id) if task_id else None,
                    "args": list(args) if args else None,
                    "kwargs": dict(kwargs) if kwargs else None,
                },
                stack_trace=tb_text,
            )
        )
    except Exception:
        import sys as _sys
        import traceback as _tb
        _tb.print_exc(file=_sys.stderr)
