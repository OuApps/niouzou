"""Refresh worker — a dedicated FastAPI app that runs the fetch+enrich
pipeline off the main API process.

Why a separate service? The pipeline is CPU/IO heavy (newspaper4k parsing,
optional LLM calls per article, batch INSERTs). Running it inside the main
uvicorn process — even as a BackgroundTask — starves incoming PWA requests
on a small Railway instance.

This service shares the API's Docker image and codebase; only the start
command and the Railway service config differ. It's intended to run with
**one replica** behind a private Railway domain (``*.railway.internal``)
with serverless / scale-to-zero enabled, so it sleeps between manual
``/admin/refresh`` triggers.

Concurrency: a single in-process ``asyncio.Lock`` is enough since there is
exactly one replica and Railway waits for in-flight requests before scaling
down. If you ever scale this out, swap the lock for
``SELECT pg_try_advisory_lock(...)`` against Postgres.
"""

import asyncio
import logging

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from niouzou.crons import enrich as cron_enrich
from niouzou.crons import fetch as cron_fetch

# uvicorn only configures its own loggers; without this our app loggers
# (niouzou.refresh_worker, niouzou.cron_fetch, niouzou.cron_enrich) emit
# nothing at INFO level — making the pipeline look stuck.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("niouzou.refresh_worker")

app = FastAPI(title="Niouzou Refresh Worker", version="0.1.0")

_lock = asyncio.Lock()


async def _run_pipeline() -> None:
    try:
        logger.info("refresh_worker: cron_fetch start")
        await cron_fetch.run()
        logger.info("refresh_worker: cron_enrich start")
        await cron_enrich.run()
        logger.info("refresh_worker: done")
    except Exception:
        logger.exception("refresh_worker: pipeline failed")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run() -> JSONResponse:
    """Trigger the fetch+enrich pipeline.

    Returns immediately with ``{"status": "already_running"}`` if a previous
    run is still in flight; otherwise spawns the pipeline as a task and
    returns ``{"status": "started"}``.
    """
    if _lock.locked():
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "already_running"},
        )

    async def _guarded() -> None:
        async with _lock:
            await _run_pipeline()

    asyncio.create_task(_guarded())
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content={"status": "started"}
    )
