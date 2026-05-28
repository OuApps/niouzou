"""Admin endpoints (E7-S16).

POST /admin/refresh triggers cron_fetch + cron_enrich back-to-back as a
background task. A module-level flag debounces concurrent runs.

NOTE: this route should be gated by ``require_admin`` once E8-S1 lands. For
now, in the single-user self-host model, every authenticated user can trigger
it.
"""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, status
from fastapi.responses import JSONResponse

from niouzou.crons import enrich as cron_enrich
from niouzou.crons import fetch as cron_fetch
from niouzou.deps import CurrentUser

router = APIRouter(prefix="/admin", tags=["admin"])

logger = logging.getLogger("niouzou.admin")

# Single-process in-memory guard — sufficient for self-host deployments. If
# scaled out, switch to an advisory lock in Postgres.
_refresh_lock = asyncio.Lock()


async def _run_refresh_pipeline() -> None:
    """Run fetch then enrich. Owns the lock for the duration."""
    if _refresh_lock.locked():
        # Defensive: BackgroundTasks already serialises, but a race on
        # spawning could in theory queue two tasks; the lock collapses them.
        logger.info("admin/refresh: another run is in flight, skipping")
        return
    async with _refresh_lock:
        try:
            logger.info("admin/refresh: cron_fetch start")
            await cron_fetch.run()
            logger.info("admin/refresh: cron_enrich start")
            await cron_enrich.run()
            logger.info("admin/refresh: done")
        except Exception:
            logger.exception("admin/refresh: pipeline failed")


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def trigger_refresh(
    user: CurrentUser, background: BackgroundTasks
) -> JSONResponse:
    """Kick off cron_fetch + cron_enrich asynchronously.

    Returns 202 immediately. If a previous run is still in flight, this is a
    no-op — the response is identical so the PWA can debounce without coupling
    to server state.
    """
    if _refresh_lock.locked():
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "already_running"},
        )
    background.add_task(_run_refresh_pipeline)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content={"status": "started"}
    )
