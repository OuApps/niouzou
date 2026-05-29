"""Admin endpoints (E7-S16).

POST /admin/refresh proxies to the ``refresh-worker`` service so the heavy
fetch+enrich pipeline doesn't run inside the API process (which would starve
PWA requests on a small Railway instance). The worker owns the
single-in-flight lock; this endpoint just forwards.
"""

import logging
import os

import httpx
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from niouzou.deps import CurrentUser

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("niouzou.admin")

# Default targets the Railway internal DNS for the refresh-worker service.
# Override locally with REFRESH_WORKER_URL=http://localhost:8001 etc.
_WORKER_URL = os.environ.get(
    "REFRESH_WORKER_URL", "http://refresh-worker.railway.internal:8000"
)


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def trigger_refresh(user: CurrentUser) -> JSONResponse:
    """Forward the refresh request to the worker service.

    Mirrors the worker's response shape (``{"status": "started"|"already_running"}``)
    so the PWA contract doesn't change.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{_WORKER_URL}/run")
        resp.raise_for_status()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED, content=resp.json()
        )
    except httpx.HTTPError as exc:
        logger.warning("admin/refresh: worker unreachable — %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "worker_unavailable"},
        )
