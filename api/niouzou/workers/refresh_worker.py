"""Refresh worker — scheduled + on-demand pipeline runner.

Why a separate service? The pipeline is CPU/IO heavy (newspaper4k parsing,
optional LLM calls per article, batch INSERTs). Running it inside the main
uvicorn process — even as a BackgroundTask — starves incoming PWA requests
on a small Railway instance.

This service shares the API's Docker image and codebase; only the start
command and the Railway service config differ. It runs as a single replica
behind a private Railway domain (``*.railway.internal``).

E8-S6 — Scheduled execution:
    Three Railway cron services used to call the cron scripts directly
    against the DB, completely bypassing this worker. That left a race
    window where ``POST /admin/refresh`` and a Railway cron could run
    ``cron_fetch``/``cron_enrich`` concurrently with no mutual exclusion.
    The worker now owns scheduling too, via APScheduler:

      * ``_guarded_run`` is shared by the scheduler AND ``POST /run`` — the
        same ``asyncio.Lock`` is acquired in both paths, so a manual trigger
        during a scheduled run (or vice versa) is debounced cleanly.
      * Settings are resolved at startup via ``SettingsService`` (DB override
        → env fallback). Live changes via ``PATCH /admin/config`` take effect
        on the next worker restart — acceptable, see EPICS.md E8-S6.

Concurrency: a single in-process ``asyncio.Lock`` is enough since there is
exactly one replica. If this service ever scales out, swap the lock for
``SELECT pg_try_advisory_lock(...)`` against Postgres.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from niouzou.crons import enrich as cron_enrich
from niouzou.crons import fetch as cron_fetch
from niouzou.crons import refresh_weights as cron_refresh_weights
from niouzou.db import session_scope
from niouzou.services.settings_service import SettingsService

# uvicorn only configures its own loggers; without this our app loggers
# (niouzou.refresh_worker, niouzou.cron_fetch, niouzou.cron_enrich) emit
# nothing at INFO level — making the pipeline look stuck.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("niouzou.refresh_worker")

_lock = asyncio.Lock()
_scheduler: AsyncIOScheduler | None = None


async def _run_pipeline() -> None:
    try:
        logger.info("refresh_worker: cron_fetch start")
        await cron_fetch.run()
        logger.info("refresh_worker: cron_enrich start")
        await cron_enrich.run()
        logger.info("refresh_worker: done")
    except Exception:
        logger.exception("refresh_worker: pipeline failed")


async def _guarded_run() -> None:
    """Acquire ``_lock`` then run the pipeline; skip cleanly if locked.

    The lock is shared with ``POST /run`` so the two entry points
    (scheduler + manual trigger) are mutually exclusive. ``_lock.locked()``
    is checked before ``await _lock.acquire()`` so we never queue a second
    run behind a slow one — if a previous run is still in flight, this one
    is dropped and reported in the logs.
    """
    if _lock.locked():
        logger.info("refresh_worker: scheduled run skipped — already running")
        return
    async with _lock:
        await _run_pipeline()


async def _refresh_weights_job() -> None:
    """Daily keyword-weight recompute. Independent of the pipeline lock."""
    try:
        logger.info("refresh_worker: cron_refresh_weights start")
        await cron_refresh_weights.run()
        logger.info("refresh_worker: cron_refresh_weights done")
    except Exception:
        logger.exception("refresh_worker: cron_refresh_weights failed")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire APScheduler with the current cron settings.

    Triggers are CronTrigger (wall-clock aligned) rather than
    IntervalTrigger so the next fire time is predictable — the PWA's
    "Next fetch" estimate in /stats (E7-S27) is computed as
    ``last_fetched_at + cron_fetch_interval`` and stays valid only when the
    real schedule is wall-clock aligned.
    """
    global _scheduler
    async with session_scope() as session:
        cfg = await SettingsService(session).get_effective()

    interval = max(1, cfg.cron_fetch_interval)
    weights_hour = cfg.cron_refresh_weights_hour

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _guarded_run,
        CronTrigger(minute=f"*/{interval}"),
        id="fetch_enrich",
        # A worker restart close to the next slot must not skip it.
        misfire_grace_time=300,
        coalesce=True,
    )
    _scheduler.add_job(
        _refresh_weights_job,
        CronTrigger(hour=weights_hour, minute=0),
        id="refresh_weights",
        # The daily job can tolerate a generous grace window — a one-hour
        # restart shouldn't make us lose a run.
        misfire_grace_time=3600,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "refresh_worker: scheduler started (fetch_enrich=*/%d min, refresh_weights=%02d:00 UTC)",
        interval,
        weights_hour,
    )
    try:
        yield
    finally:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _scheduler = None


app = FastAPI(title="Niouzou Refresh Worker", version="0.1.0", lifespan=_lifespan)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run() -> JSONResponse:
    """Trigger the fetch+enrich pipeline.

    Returns immediately with ``{"status": "already_running"}`` if a previous
    run is still in flight; otherwise spawns ``_guarded_run`` as a task and
    returns ``{"status": "started"}``. The exact same ``_lock`` guards the
    scheduled path, so the two entry points never race.
    """
    if _lock.locked():
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "already_running"},
        )
    asyncio.create_task(_guarded_run())
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content={"status": "started"}
    )
