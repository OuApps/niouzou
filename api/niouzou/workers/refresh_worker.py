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

E10-S1 — Pipeline telemetry:
    Every fetch+enrich cycle is now recorded in ``pipeline_runs``: when it
    started, when it ended, how many articles were processed, and whether it
    failed. The previous design exposed no run history — "Feed may be
    stalled" was a faux-positive driven by the last article's ``created_at``,
    which lit up whenever a healthy cron tick produced nothing new.

    The worker drives the per-article loop itself (rather than calling
    ``cron_enrich.run()``) so it can update the run row after each article.
    Each article briefly flips to ``'enriching'`` in its own short
    transaction before the heavy enrichment work — that transient state is
    what ``/stats`` reads to render the live progress bar.

    A reaper at startup resets any article left in ``'enriching'`` from a
    previous worker crash. Without it, those articles would be invisible to
    both the feed (status filter) and the next pipeline run (pending filter).

Concurrency: a single in-process ``asyncio.Lock`` is enough since there is
exactly one replica. If this service ever scales out, swap the lock for
``SELECT pg_try_advisory_lock(...)`` against Postgres.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import update

from niouzou.config import get_settings
from niouzou.crons import enrich as cron_enrich
from niouzou.crons import fetch as cron_fetch
from niouzou.crons import refresh_weights as cron_refresh_weights
from niouzou.db import session_scope
from niouzou.models import Article, PipelineRun
from niouzou.models.article import STATUS_ENRICHING, STATUS_PENDING
from niouzou.models.pipeline_run import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
)
from niouzou.models import CompactionRun
from niouzou.models.compaction_run import STATUS_PREVIEW as _COMPACT_PREVIEW
from niouzou.services.compaction_service import CompactionService
from niouzou.services.openrouter_client import OpenRouterClient
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
# E10-S3 — separate lock for the compaction *preview* phase (LLM call only,
# no DB write). Kept distinct from ``_lock`` so a long LLM grouping call
# doesn't freeze the fetch+enrich pipeline. The ``apply`` phase uses
# ``_lock`` because it rewrites ``article_keywords`` and must not race the
# pipeline's writes.
_compact_lock = asyncio.Lock()
_scheduler: AsyncIOScheduler | None = None


# ── pipeline_runs persistence helpers ─────────────────────────────────────


async def _create_pipeline_run() -> uuid.UUID:
    """Insert a ``status='running'`` row and return its id."""
    async with session_scope() as session:
        run = PipelineRun(status=STATUS_RUNNING)
        session.add(run)
        await session.flush()
        return run.id


async def _update_pipeline_run(run_id: uuid.UUID, **fields: object) -> None:
    """Patch a few columns on an in-flight run (no completed_at)."""
    if not fields:
        return
    async with session_scope() as session:
        await session.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(**fields)
        )


async def _finalize_pipeline_run(
    run_id: uuid.UUID,
    *,
    status_value: str,
    articles_fetched: int,
    articles_enriched: int,
    articles_failed: int,
    articles_in_run: int,
    total_duration_s: float,
    error: str | None,
) -> None:
    """Write the terminal row state. ``avg_s_per_article`` derived per spec.

    Per E10-S1: ``avg = total_duration_s / max(1, articles_enriched)``. When
    nothing was enriched (denominator clamped to 1), the value equals the
    total run duration — the PWA suppresses the display in that case.
    """
    avg = total_duration_s / max(1, articles_enriched)
    async with session_scope() as session:
        await session.execute(
            update(PipelineRun)
            .where(PipelineRun.id == run_id)
            .values(
                status=status_value,
                completed_at=datetime.now(timezone.utc),
                articles_fetched=articles_fetched,
                articles_enriched=articles_enriched,
                articles_failed=articles_failed,
                articles_in_run=articles_in_run,
                total_duration_s=total_duration_s,
                avg_s_per_article=avg,
                error=error,
            )
        )


async def _reaper_reset_enriching() -> int:
    """Recover articles stuck in ``'enriching'`` from a previous crash.

    Returns the number of rows reset. Called once at lifespan startup, before
    the scheduler fires — guarantees the first scheduled run sees a clean
    pending set. An in-flight worker that crashed mid-enrichment will leave
    rows in this transient status; without the reaper they'd be invisible to
    every code path.
    """
    async with session_scope() as session:
        result = await session.execute(
            update(Article)
            .where(Article.status == STATUS_ENRICHING)
            .values(status=STATUS_PENDING)
        )
        return result.rowcount or 0


# ── article-level status transitions ──────────────────────────────────────


async def _mark_enriching(article_id: uuid.UUID) -> bool:
    """Flip ``pending → enriching`` in its own short transaction.

    Returns True when the flip happened, False if the article disappeared or
    was already past pending (defensive — concurrent runs are gated by
    ``_lock`` but the check costs nothing). The commit is intentional: it
    makes the article visible to ``/stats`` as in-progress without polling
    memory.
    """
    async with session_scope() as session:
        article = await session.get(Article, article_id)
        if article is None or article.status != STATUS_PENDING:
            return False
        article.status = STATUS_ENRICHING
        return True


async def _reset_to_pending(article_id: uuid.UUID) -> None:
    """Rollback ``enriching → pending`` after a failed enrichment.

    The article is freed for a future run instead of staying stuck in the
    transient status (which would require a worker restart to recover via
    the reaper).
    """
    try:
        async with session_scope() as session:
            article = await session.get(Article, article_id)
            if article is not None and article.status == STATUS_ENRICHING:
                article.status = STATUS_PENDING
    except Exception:
        # Best effort: the next reaper pass will pick this up.
        logger.exception(
            "refresh_worker: failed to reset article %s back to pending",
            article_id,
        )


# ── main pipeline ─────────────────────────────────────────────────────────


async def _run_pipeline() -> None:
    """Fetch + enrich one batch, recording telemetry in ``pipeline_runs``.

    The run row is created up front so a catastrophic early failure (e.g.
    Miniflux unreachable in ``cron_fetch``) is still observable via /stats.
    """
    run_id = await _create_pipeline_run()
    started = time.perf_counter()
    articles_fetched = 0
    articles_enriched = 0
    articles_failed = 0
    articles_in_run = 0
    error: str | None = None
    try:
        logger.info("refresh_worker: pipeline run %s started", run_id)

        # 1. Fetch — articles_fetched is the count of entries we just ingested.
        articles_fetched = await cron_fetch.run()
        await _update_pipeline_run(run_id, articles_fetched=articles_fetched)

        # 2. Snapshot pending capped to batch size; freeze articles_in_run so a
        #    concurrent fetch ingesting more pending rows doesn't make the
        #    progress bar denominator drift mid-run.
        settings = get_settings()
        async with cron_enrich.enrichment_resources() as resources:
            async with session_scope() as session:
                pending_ids = await cron_enrich._pending_article_ids(
                    session, settings.enrich_batch_size
                )
            articles_in_run = len(pending_ids)
            await _update_pipeline_run(run_id, articles_in_run=articles_in_run)
            logger.info(
                "refresh_worker: %d pending article(s) to enrich",
                articles_in_run,
            )

            # 3. Per-article enrichment. Each article is wrapped in two short
            #    transactions: 'enriching' transition (committed for /stats
            #    visibility) and the actual work (committed on success).
            for idx, article_id in enumerate(pending_ids, start=1):
                t0 = time.perf_counter()
                logger.info(
                    "refresh_worker: [%d/%d] start %s",
                    idx,
                    articles_in_run,
                    article_id,
                )

                # The mark step is outside the try below: a failure here
                # means the article was never claimed, so there's nothing
                # to reset and nothing to count.
                if not await _mark_enriching(article_id):
                    logger.info(
                        "refresh_worker: [%d/%d] skipped (already handled)",
                        idx,
                        articles_in_run,
                    )
                    continue

                counters_changed = False
                try:
                    enriched_ok = False
                    async with session_scope() as session:
                        article = await session.get(Article, article_id)
                        if article is not None and article.status == STATUS_ENRICHING:
                            await cron_enrich.enrich_article(
                                session,
                                article,
                                enrichment=resources.enrichment,
                                ai_scoring=resources.ai_scoring,
                                tfidf_scoring=resources.tfidf_scoring,
                                openrouter_model=resources.openrouter_model,
                            )
                            enriched_ok = True

                    if enriched_ok:
                        articles_enriched += 1
                        counters_changed = True
                        logger.info(
                            "refresh_worker: [%d/%d] done in %.2fs",
                            idx,
                            articles_in_run,
                            time.perf_counter() - t0,
                        )
                    else:
                        # Defensive: the article disappeared or its status
                        # drifted between our mark and the re-fetch. Release
                        # the marker we set so it isn't stuck in 'enriching';
                        # don't count this as enriched OR failed since no
                        # work was attempted. _reset_to_pending is idempotent
                        # on non-'enriching' statuses.
                        logger.info(
                            "refresh_worker: [%d/%d] skipped after mark — "
                            "concurrent state change for %s",
                            idx,
                            articles_in_run,
                            article_id,
                        )
                        await _reset_to_pending(article_id)
                except Exception:
                    articles_failed += 1
                    counters_changed = True
                    logger.exception(
                        "refresh_worker: [%d/%d] failed for %s",
                        idx,
                        articles_in_run,
                        article_id,
                    )
                    await _reset_to_pending(article_id)

                # Only persist when the counters actually moved — avoids a
                # redundant DB roundtrip per skipped article. /stats can
                # afford to wait one iteration if a skip happens.
                if counters_changed:
                    await _update_pipeline_run(
                        run_id,
                        articles_enriched=articles_enriched,
                        articles_failed=articles_failed,
                    )

        logger.info(
            "refresh_worker: pipeline done — fetched=%d enriched=%d failed=%d",
            articles_fetched,
            articles_enriched,
            articles_failed,
        )
    except Exception as exc:
        logger.exception("refresh_worker: pipeline failed")
        error = f"{type(exc).__name__}: {exc}"
    finally:
        await _finalize_pipeline_run(
            run_id,
            status_value=STATUS_FAILED if error else STATUS_COMPLETED,
            articles_fetched=articles_fetched,
            articles_enriched=articles_enriched,
            articles_failed=articles_failed,
            articles_in_run=articles_in_run,
            total_duration_s=time.perf_counter() - started,
            error=error,
        )


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
    IntervalTrigger so the next fire time is predictable — the PWA renders
    "Next run" against the live ``cron_fetch_interval_minutes`` from /stats.

    The reaper runs once here, before the scheduler starts, so any article
    left in ``'enriching'`` by a previous crash is rolled back to pending
    before the first scheduled run starts a fresh batch.
    """
    global _scheduler
    reaped = await _reaper_reset_enriching()
    if reaped:
        logger.info(
            "refresh_worker: reaper reset %d enriching → pending on startup",
            reaped,
        )

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


# ── Compaction endpoints (E10-S3) ────────────────────────────────────────


class _CompactApplyBody(BaseModel):
    id: uuid.UUID


@app.post("/compact/preview", status_code=status.HTTP_202_ACCEPTED)
async def compact_preview() -> JSONResponse:
    """Generate a keyword-merge preview (LLM only — no DB write yet).

    ``_compact_lock`` is held for the duration of the LLM call so a second
    preview can't race the first; the pipeline ``_lock`` is left free so
    fetch+enrich keeps running while the LLM is thinking.
    """
    if _compact_lock.locked():
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "already_running"},
        )
    async with _compact_lock:
        async with session_scope() as session:
            cfg = await SettingsService(session).get_effective()
        client = OpenRouterClient.from_overrides(
            cfg.openrouter_api_key, cfg.openrouter_model
        )
        if client is None:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "ai_disabled",
                    "message": "Compaction requires an OpenRouter API key.",
                },
            )
        try:
            async with session_scope() as session:
                run = await CompactionService(session, client).preview()
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "id": str(run.id),
                        "groups": run.groups_json,
                    },
                )
        finally:
            client.close()


@app.post("/compact/apply", status_code=status.HTTP_202_ACCEPTED)
async def compact_apply(body: _CompactApplyBody) -> JSONResponse:
    """Apply a previously-generated preview.

    Uses the *pipeline* ``_lock`` (not ``_compact_lock``): the apply rewrites
    ``article_keywords`` and reruns the weight recompute. Doing that while a
    fetch+enrich pipeline is also writing rows would corrupt both.

    The run id is validated *before* the 202 is returned so a stale id from
    the admin UI (already applied / rejected / unknown) surfaces as a 404
    instead of silently logging a background failure ten seconds later.
    """
    async with session_scope() as session:
        run = await session.get(CompactionRun, body.id)
        if run is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "not_found", "message": "Compaction run not found"},
            )
        if run.status != _COMPACT_PREVIEW:
            # 409 because the resource exists but is in a terminal state — the
            # caller's request is well-formed but no longer applicable.
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "error": "invalid_state",
                    "message": f"Compaction run is not a preview (status={run.status!r})",
                },
            )

    if _lock.locked():
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "already_running"},
        )
    asyncio.create_task(_apply_in_background(body.id))
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content={"status": "started"}
    )


async def _apply_in_background(run_id: uuid.UUID) -> None:
    """Acquire the pipeline lock and run ``CompactionService.apply``."""
    async with _lock:
        try:
            async with session_scope() as session:
                await CompactionService(session).apply(run_id)
                logger.info("refresh_worker: compaction %s applied", run_id)
        except Exception:
            logger.exception(
                "refresh_worker: compaction apply failed for %s", run_id
            )


@app.delete(
    "/compact/{run_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def compact_reject(run_id: uuid.UUID) -> JSONResponse:
    """Mark a preview as rejected (no DB rewrites)."""
    try:
        async with session_scope() as session:
            await CompactionService(session).reject(run_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "not_found", "message": str(exc)},
        )
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)


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
