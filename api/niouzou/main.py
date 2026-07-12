"""FastAPI application entry point.

Run with: ``uv run uvicorn niouzou.main:app --reload`` from the ``api/`` dir.
All resource routers are mounted under ``/api/v1`` (docs/API_SPEC.md); ``/health``
sits at the root for load balancers and the Docker/Railway healthcheck.
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from niouzou.errors import (
    APIError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from niouzou.routers import (
    admin,
    articles,
    auth,
    explore,
    feed,
    feedback,
    keywords,
    mcp,
    me,
    saved,
    sources,
    stats,
)

app = FastAPI(title="Niouzou API", version="0.1.0")

# Allow the PWA (any origin in dev, tighten in prod via CORS_ORIGINS env var)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

API_PREFIX = "/api/v1"
for module in (
    auth,
    sources,
    feed,
    feedback,
    articles,
    saved,
    explore,
    keywords,
    me,
    stats,
    admin,
):
    app.include_router(module.router, prefix=API_PREFIX)

# E22 — the MCP server speaks a different protocol (JSON-RPC) and auth scheme
# (service account key), so it's mounted at the root ``/mcp`` rather than under
# the versioned REST prefix. MCP clients are configured with this URL directly.
app.include_router(mcp.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
