"""Best-effort HTTP client for the refresh-worker service.

The worker owns the single-in-flight pipeline lock (see
``workers/refresh_worker.py``); the API only ever asks it to *start* a run.
Kept separate from any request's DB session — these are fire-and-forget side
effects whose failure must never break the caller's primary action.
"""

import logging
import os

import httpx

logger = logging.getLogger("niouzou.worker_client")

# Default targets the Railway internal DNS for the refresh-worker service.
# Override locally with REFRESH_WORKER_URL=http://localhost:8001 etc.
WORKER_URL = os.environ.get(
    "REFRESH_WORKER_URL", "http://refresh-worker.railway.internal:8000"
)


async def trigger_pipeline_run() -> str:
    """Kick the worker's fetch+enrich pipeline. Best-effort, never raises.

    The worker debounces concurrent runs via its own lock, so calling this on
    every source add is safe — a run already in flight returns
    ``already_running``. Returns the worker's status string, or
    ``worker_unavailable`` when the worker can't be reached (so the caller can
    log/ignore rather than fail).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{WORKER_URL}/run")
        resp.raise_for_status()
        run_status = resp.json().get("status", "started")
        logger.info("trigger_pipeline_run: worker responded %s", run_status)
        return run_status
    except httpx.HTTPError as exc:
        logger.warning("trigger_pipeline_run: worker unreachable — %s", exc)
        return "worker_unavailable"
