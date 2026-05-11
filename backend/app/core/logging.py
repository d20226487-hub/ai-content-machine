"""Structured logging — pretty in dev, JSON in prod.

Switched at startup based on `LOG_FORMAT` (`pretty` | `json`). Uses stdlib
`logging` so every library that already logs (uvicorn, sqlalchemy, celery,
httpx, ours) lands in one stream with consistent fields.

The JSON formatter has no third-party dep — keeps requirements.txt tight.
For dev we use a compact text formatter that includes the request_id when
available so you can `grep` correlated lines.

Per-request context: `RequestIdMiddleware` picks an id from the inbound
`X-Request-ID` header (trusted because Caddy sets it) or generates a new
one, stashes it on `request.state.request_id`, and exposes it to log
records via a `contextvars`-based filter.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


# Bound at request start (api) or task start (worker). Empty string means
# "no current correlation id" — the formatter omits the field then.
_request_id: ContextVar[str] = ContextVar("acm_request_id", default="")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


# --- formatters ----------------------------------------------------------

_BASE_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Stable key order: timestamp/level/logger/msg
    first, then any record extras, then exception info."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S")
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = get_request_id()
        if rid:
            payload["request_id"] = rid

        # Anything attached via `logger.info("x", extra={"foo": ...})`.
        for key, value in record.__dict__.items():
            if key in _BASE_FIELDS or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class PrettyFormatter(logging.Formatter):
    """Compact, human-readable: TIME LVL logger | request_id | msg"""

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, datefmt="%H:%M:%S")
        rid = get_request_id()
        prefix = f"{ts} {record.levelname:<5} {record.name}"
        if rid:
            prefix += f" [{rid[:8]}]"
        prefix += f" | {record.getMessage()}"
        if record.exc_info:
            prefix += "\n" + self.formatException(record.exc_info)
        return prefix


# --- public configuration ------------------------------------------------

def configure_logging(level: str = "INFO", fmt: str = "pretty") -> None:
    """Idempotent. Replaces handlers on the root logger."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else PrettyFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Tame the chattiest libs unless the operator opted into DEBUG explicitly.
    quiet_level = max(logging.WARNING, root.level)
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(quiet_level)


# --- middleware ----------------------------------------------------------

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a request_id for the duration of each request.

    Trust order: inbound `X-Request-ID` header (set by Caddy or the upstream
    LB), then a fresh UUID. The id is mirrored back on the response so the
    operator can correlate browser-side errors with server logs.
    """

    HEADER = "x-request-id"

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger = logging.getLogger("acm.access")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get(self.HEADER) or uuid.uuid4().hex
        token = _request_id.set(rid)
        request.state.request_id = rid
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.monotonic() - started) * 1000)
            # Let the global error handler still run; we just emit one line
            # so the duration + path are searchable even on 500s.
            self._logger.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            _request_id.reset(token)

        duration_ms = int((time.monotonic() - started) * 1000)
        response.headers[self.HEADER] = rid
        # One structured line per request — the access log replacement.
        # Skip /health to avoid drowning the log in healthcheck traffic.
        if request.url.path != "/health":
            self._logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response
