import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    auth,
    categories,
    domains as domains_router,
    errors as errors_router,
    generate,
    generations as generations_router,
    health,
    library,
    prompts,
    publish as publish_router,
    publish_bulk as publish_bulk_router,
    settings as settings_router,
    tags,
    users as users_module,
)
from app.core.config import get_settings
from app.services.error_log import log_error_standalone

settings = get_settings()

app = FastAPI(title="AI Content Machine", version="0.1.0")

# gzip larger responses; ~85% reduction on HTML/JSON-heavy payloads.
# Threshold of 1024 bytes skips the overhead for tiny replies.
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        # Intentional 4xx/redirects — re-raise so FastAPI's default handler runs.
        raise exc

    user_id = None
    user = getattr(request.state, "user", None)
    if user is not None:
        user_id = getattr(user, "id", None)

    await log_error_standalone(
        source="api",
        category="unhandled",
        message=f"{type(exc).__name__}: {exc}",
        user_id=user_id,
        status_code=500,
        context={
            "path": str(request.url.path),
            "method": request.method,
            "query": str(request.url.query) or None,
        },
        stack_trace="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    return JSONResponse(
        status_code=500, content={"detail": "Internal server error"}
    )

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(settings_router.router)
app.include_router(users_module.users_router)
app.include_router(users_module.roles_router)
app.include_router(categories.router)
app.include_router(tags.router)
app.include_router(prompts.router)
app.include_router(generate.router)
app.include_router(generations_router.router)
app.include_router(library.router)
app.include_router(errors_router.router)
app.include_router(domains_router.router)
app.include_router(publish_router.router)
app.include_router(publish_bulk_router.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": "AI Content Machine", "version": "0.1.0"}
