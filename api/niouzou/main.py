"""FastAPI application entry point.

Run with: ``uv run uvicorn niouzou.main:app --reload`` from the ``api/`` dir.
All resource routers are mounted under ``/api/v1`` (docs/API_SPEC.md); ``/health``
sits at the root for load balancers and the Docker/Railway healthcheck.
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from niouzou.config import get_settings
from niouzou.errors import (
    APIError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from niouzou.mcp_app import mcp_asgi_app, mcp_lifespan
from niouzou.routers import (
    admin,
    articles,
    auth,
    explore,
    feed,
    feedback,
    keywords,
    me,
    saved,
    sources,
    stats,
)

# ``mcp_lifespan`` runs the FastMCP Streamable HTTP session manager for the
# app's lifetime (E22).
app = FastAPI(title="Niouzou API", version="0.1.0", lifespan=mcp_lifespan)

# Allow the PWA to call the API cross-origin. Defaults to any origin (dev +
# self-hosting); tighten in a hosted deployment via the CORS_ORIGINS env var,
# e.g. CORS_ORIGINS=https://niouzou.galaxou.com (comma-separated for several).
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
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


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# E22 — the FastMCP server speaks a different protocol (MCP / JSON-RPC) and
# auth scheme (service account key), so it lives at the root ``/mcp`` rather
# than under the versioned REST prefix. Mounted LAST as a root-level catch-all
# (empty prefix) so it can't shadow the REST routes or ``/health``: ``POST
# /mcp`` hits the handler directly with no trailing-slash redirect, while the
# middleware restricts itself to ``/mcp`` and ``/mcp/`` and 404s everything
# else, leaving the REST 404s untouched.
app.mount("", mcp_asgi_app)
