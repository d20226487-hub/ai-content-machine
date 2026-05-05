import asyncio

from celery import Celery
from celery.signals import task_failure

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "acm",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.example",
        "app.tasks.bulk_generation",
        "app.tasks.publish_bulk",
        "app.tasks.publish_single",
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
)


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
