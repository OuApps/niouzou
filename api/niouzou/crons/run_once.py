"""run_once — the one-shot pipeline child that does the heavy work, then dies (E20).

Why this module exists (the frugal-worker re-architecture, EPIC 20):
    The refresh worker used to run the whole fetch + enrich pipeline *in-process*.
    That process is always-on (uvicorn + APScheduler), so once ``torch`` +
    ``sentence-transformers`` were imported and the ~1.2 GB Qwen3 embedding
    model loaded, the RSS never came back down — torch's caching allocator and
    glibc arenas keep the pages, and ``unload`` + ``gc.collect`` (E17-S4) don't
    return them to the OS. Railway bills real usage, so we paid for a sleeping
    model 24/7 while the model is only useful a few minutes a day.

    The only reliable way to give the RAM back to the OS is to **kill the
    process**. So the heavy pipeline now lives here, in a short-lived child the
    parent worker spawns per run (``python -m niouzou.crons.run_once``). This is
    the *only* process that imports torch and loads the model; when it exits the
    OS reclaims 100 % of its RAM. The parent (``workers/refresh_worker.py``)
    stays light (~120-150 MB, never imports torch) and only supervises.

Two modes:
    * default          → one fetch + enrich cycle, telemetry into ``pipeline_runs``.
    * ``--nightly``    → ``cron_nightly_refresh`` (weights recompute + dual-score
                         rescore). It does NOT load the embedding model (the smart
                         rescore runs in pgvector on stored vectors); running it as
                         a subprocess is purely for isolation + uniformity (E20-S3).

Lifecycle: run the work, close the Postgres pool cleanly (``engine.dispose``),
then exit. A non-zero exit code signals a fatal failure to the parent (logged).

Tests never spawn this as a subprocess and never load the real model — they call
``_run_pipeline`` / ``run_nightly`` directly with the cron functions stubbed and
the embedder injected (see ``tests/conftest.py`` tripwire).
"""

import argparse
import asyncio
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import update

from niouzou.config import get_settings
from niouzou.crons import enrich as cron_enrich
from niouzou.crons import fetch as cron_fetch
from niouzou.crons import nightly_refresh as cron_nightly_refresh
from niouzou.db import engine, session_scope
from niouzou.models import Article, PipelineRun
from niouzou.models.article import STATUS_ENRICHING, STATUS_PENDING
from niouzou.models.pipeline_run import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
)

logger = logging.getLogger("niouzou.run_once")


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
    """Recover articles stuck in ``'enriching'`` from a previous crash/kill.

    Returns the number of rows reset. Called at child startup (and by the
    parent worker at its own startup) before any fresh batch. A child killed
    on timeout mid-enrichment leaves rows in this transient status; without the
    reaper they'd be invisible to every code path (feed status filter + the
    next run's pending filter).
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
    was already past pending (defensive — concurrent runs are gated by the
    parent's ``_lock`` but the check costs nothing). The commit is intentional:
    it makes the article visible to ``/stats`` as in-progress without polling
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
    transient status (which would require a reaper pass to recover).
    """
    try:
        async with session_scope() as session:
            article = await session.get(Article, article_id)
            if article is not None and article.status == STATUS_ENRICHING:
                article.status = STATUS_PENDING
    except Exception:
        # Best effort: the next reaper pass will pick this up.
        logger.exception(
            "run_once: failed to reset article %s back to pending",
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
        logger.info("run_once: pipeline run %s started", run_id)

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
                "run_once: %d pending article(s) to enrich",
                articles_in_run,
            )

            # 3. Per-article enrichment. Each article is wrapped in two short
            #    transactions: 'enriching' transition (committed for /stats
            #    visibility) and the actual work (committed on success).
            for idx, article_id in enumerate(pending_ids, start=1):
                t0 = time.perf_counter()
                logger.info(
                    "run_once: [%d/%d] start %s",
                    idx,
                    articles_in_run,
                    article_id,
                )

                # The mark step is outside the try below: a failure here
                # means the article was never claimed, so there's nothing
                # to reset and nothing to count.
                if not await _mark_enriching(article_id):
                    logger.info(
                        "run_once: [%d/%d] skipped (already handled)",
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
                                scoring=resources.scoring,
                                openrouter_model=resources.openrouter_model,
                                embedder=resources.embedder,
                            )
                            enriched_ok = True

                    if enriched_ok:
                        articles_enriched += 1
                        counters_changed = True
                        logger.info(
                            "run_once: [%d/%d] done in %.2fs",
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
                            "run_once: [%d/%d] skipped after mark — "
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
                        "run_once: [%d/%d] failed for %s",
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
            "run_once: pipeline done — fetched=%d enriched=%d failed=%d",
            articles_fetched,
            articles_enriched,
            articles_failed,
        )
    except Exception as exc:
        logger.exception("run_once: pipeline failed")
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


# ── child entry points ─────────────────────────────────────────────────────


async def run_pipeline() -> None:
    """Child entry: self-reap orphans left by a killed sibling, then one cycle.

    The parent reaps at its own (rare) startup; this covers the common case
    where a previous child was killed on timeout mid-enrichment.
    """
    reaped = await _reaper_reset_enriching()
    if reaped:
        logger.info("run_once: self-reaper reset %d enriching → pending", reaped)
    await _run_pipeline()


async def run_nightly() -> None:
    """Child entry: daily weights recompute + dual-score rescore (E16-S9).

    No embedding model is loaded here — the smart rescore runs in pgvector on
    already-stored vectors. Run as a subprocess only for isolation/uniformity.
    """
    logger.info("run_once: cron_nightly_refresh start")
    await cron_nightly_refresh.run()
    logger.info("run_once: cron_nightly_refresh done")


async def _main_async(*, nightly: bool) -> None:
    """Run the requested job, then close the Postgres pool in the same loop.

    Disposing inside this loop (not a fresh one) avoids asyncpg
    'connection bound to a different loop' warnings — the connections were
    created on this loop.
    """
    try:
        if nightly:
            await run_nightly()
        else:
            await run_pipeline()
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(prog="niouzou.crons.run_once")
    parser.add_argument(
        "--nightly",
        action="store_true",
        help="run cron_nightly_refresh instead of the fetch+enrich pipeline",
    )
    args = parser.parse_args()

    try:
        asyncio.run(_main_async(nightly=args.nightly))
    except Exception:
        logger.exception("run_once: fatal error")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
