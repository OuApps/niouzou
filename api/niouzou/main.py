"""FastAPI application entry point.

Run with: ``uv run uvicorn niouzou.main:app --reload`` from the ``api/`` dir.
All resource routers are mounted under ``/api/v1`` (docs/API_SPEC.md); ``/health``
sits at the root for load balancers and the Docker/Railway healthcheck.
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from niouzou.errors import (
    APIError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from niouzou.routers import (
    articles,
    auth,
    feed,
    feedback,
    keywords,
    saved,
    sources,
)

app = FastAPI(title="Niouzou API", version="0.1.0")

app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

API_PREFIX = "/api/v1"
for module in (auth, sources, feed, feedback, articles, saved, keywords):
    app.include_router(module.router, prefix=API_PREFIX)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
