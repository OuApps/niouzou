"""cron_enrich — extract content, summarise, score pending articles (E5).

Run with: ``uv run python -m niouzou.crons.enrich`` (or via the cron container).

Per pending article:
  1. Extract clean content with newspaper4k, falling back to the RSS body.
  2. Summarise — LLM (summary_short + summary_executive) when AI is on, else a
     newspaper-derived summary_short.
  3. Extract + store keywords via ScoringService (the AI scorer when a key is
     set; on LLM failure, retry twice then fall back to TF-IDF — E10-S1).
  4. Score the article for its source's owner and freeze the relevance_score.
  5. Mark the article ``enriched``.

Persistence and scoring maths are NOT reimplemented here — steps 3–4 delegate
to ScoringService (Epic 3). The cron only orchestrates and owns the article
status transition.

Per-user scoring scope (E5-S2 open item): an article belongs to exactly one
source, which belongs to exactly one user, and the feed only ever surfaces an
article to that source's owner. So we score for that single owner — who, by
construction, registered before the source existed.

E10-S1 — the refresh worker drives the pipeline loop directly (so it can
record per-article telemetry into ``pipeline_runs``); this module now exposes
``enrichment_resources()`` as a reusable context manager. ``run()`` is kept
for the CLI / one-shot invocation path and uses the same helper internally.

Each article is enriched in its own transaction so one failure can't roll back
a whole batch. Blocking network calls (newspaper, LLM) run off the event loop
via asyncio.to_thread.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.config import get_settings
from niouzou.db import session_scope
from niouzou.models import Article, ArticleKeyword, Source
from niouzou.models.article import STATUS_ENRICHED, STATUS_PENDING
from niouzou.scoring import ScoringPipeline, TFIDFScorer
from niouzou.services.enrichment_service import EnrichmentService
from niouzou.services.openrouter_client import OpenRouterClient
from niouzou.services.scoring_service import ScoringService
from niouzou.services.settings_service import SettingsService

logger = logging.getLogger("niouzou.cron_enrich")


@dataclass(slots=True)
class EnrichmentResources:
    """Services needed to enrich one article — built once per run."""

    enrichment: EnrichmentService
    ai_scoring: ScoringService
    tfidf_scoring: ScoringService
    # OpenRouter model id snapshotted at the start of the run (E10-S2). Used
    # to stamp ``articles.enrichment_model`` on the AI path; ``None`` when AI
    # is disabled for this run (TF-IDF native path).
    openrouter_model: str | None = None


async def _pending_article_ids(session: AsyncSession, limit: int) -> list[uuid.UUID]:
    """Oldest pending article ids first (FIFO enrichment)."""
    rows = await session.execute(
        select(Article.id)
        .where(Article.status == STATUS_PENDING)
        .order_by(Article.created_at)
        .limit(limit)
    )
    return list(rows.scalars().all())


# Top N existing keywords injected into every enrichment prompt for this run
# (E10-S2). 200 is a balance: enough to cover the main entities/domains the
# instance has seen, low enough to fit in the prompt budget (~1.5kB) and to
# stay under the prompt-cache hash boundary as the vocab grows.
_VOCAB_INJECTION_TOP_N = 200


async def _load_top_keywords(session: AsyncSession, limit: int) -> list[str]:
    """Most-frequent ``article_keywords.term`` strings, ordered by count desc.

    Called once per cron run; cached on ``EnrichmentService._vocab``. Empty
    list on a fresh instance is fine — the prompt just skips the line.
    """
    rows = await session.execute(
        select(ArticleKeyword.term)
        .group_by(ArticleKeyword.term)
        .order_by(func.count().desc(), ArticleKeyword.term.asc())
        .limit(limit)
    )
    return list(rows.scalars().all())


@asynccontextmanager
async def enrichment_resources() -> AsyncIterator[EnrichmentResources]:
    """Build the per-run enrichment services and close the LLM client on exit.

    Admin overrides are snapshotted once: a long pipeline run sees a consistent
    view even if the admin updates the DB mid-run. The refresh worker uses this
    directly to drive its per-article loop (E10-S1); ``cron_enrich.run()``
    wraps it for the CLI entry point.
    """
    async with session_scope() as cfg_session:
        effective = await SettingsService(cfg_session).get_effective()
        vocab = await _load_top_keywords(cfg_session, _VOCAB_INJECTION_TOP_N)

    client = OpenRouterClient.from_overrides(
        effective.openrouter_api_key, effective.openrouter_model
    )
    enrichment = EnrichmentService(client)
    enrichment.set_vocab(vocab)
    tfidf_scoring = ScoringService(
        ScoringPipeline(TFIDFScorer()),
        max_keywords_per_article=effective.max_keywords_per_article,
    )
    if client is None:
        ai_scoring = tfidf_scoring
    else:
        from niouzou.scoring.ai_keyword import AIKeywordScorer

        ai_scoring = ScoringService(
            ScoringPipeline(AIKeywordScorer(client)),
            max_keywords_per_article=effective.max_keywords_per_article,
        )

    logger.info(
        "cron_enrich: resources ready (ai_enabled=%s, model=%s, vocab_terms=%d)",
        enrichment.ai_enabled,
        effective.openrouter_model if client is not None else "n/a",
        len(vocab),
    )
    try:
        yield EnrichmentResources(
            enrichment=enrichment,
            ai_scoring=ai_scoring,
            tfidf_scoring=tfidf_scoring,
            openrouter_model=(
                effective.openrouter_model if client is not None else None
            ),
        )
    finally:
        if client is not None:
            client.close()


async def enrich_article(
    session: AsyncSession,
    article: Article,
    *,
    enrichment: EnrichmentService,
    ai_scoring: ScoringService,
    tfidf_scoring: ScoringService,
    openrouter_model: str | None = None,
) -> None:
    """Enrich a single article in the given (open) transaction.

    The AI path uses a single combined LLM call (summaries + keywords) via
    ``EnrichmentService.generate_enrichment`` — half the OpenRouter roundtrips
    of the previous design. On LLM failure (or AI off), summaries fall back to
    the newspaper-derived first sentences and keywords come from TF-IDF.
    """
    owner_id = await session.scalar(
        select(Source.user_id).where(Source.id == article.source_id)
    )
    if owner_id is None:
        # Orphaned article (source deleted) — nothing to score for.
        logger.warning("enrich: no source owner for article %s, skipping", article.id)
        return

    # 1. Content extraction (blocking) off the event loop.
    t0 = time.perf_counter()
    logger.info("enrich[%s]: extracting content from %s", article.id, article.url)
    extracted = await asyncio.to_thread(
        enrichment.extract_content, article.url, rss_fallback=article.content
    )
    logger.info(
        "enrich[%s]: content extracted (%d chars) in %.2fs",
        article.id,
        len(extracted.content or ""),
        time.perf_counter() - t0,
    )
    if extracted.content:
        article.content = extracted.content
    if extracted.og_image_url and not article.og_image_url:
        article.og_image_url = extracted.og_image_url

    # 2. Combined LLM call: summaries + keywords in one roundtrip.
    t0 = time.perf_counter()
    logger.info("enrich[%s]: generating enrichment (summaries + keywords)...", article.id)
    enriched = await asyncio.to_thread(
        enrichment.generate_enrichment, article.title, article.content
    )
    logger.info(
        "enrich[%s]: enrichment generated in %.2fs (short=%d, exec=%d, keywords=%s)",
        article.id,
        time.perf_counter() - t0,
        len(enriched.summary_short or ""),
        len(enriched.summary_executive or ""),
        len(enriched.keywords) if enriched.keywords is not None else "n/a",
    )
    if not enriched.summary_short:
        enriched.summary_short = extracted.fallback_summary
    article.summary_short = enriched.summary_short
    article.summary_executive = enriched.summary_executive

    # 3. Keyword persistence — AI keywords when the combined call returned
    # some, TF-IDF fallback otherwise. ``keywords is None`` signals the LLM
    # call itself failed (or AI is off); an empty list means it ran cleanly
    # but had nothing useful — we still treat that as needing TF-IDF.
    t0 = time.perf_counter()
    if enriched.keywords:
        await ai_scoring.store_keywords(session, article, enriched.keywords)
        used, method, ai_error = ai_scoring, "ai", None
    else:
        if enriched.keywords is None and enrichment.ai_enabled:
            ai_error = "LLM enrichment call failed or returned no keywords"
            logger.warning(
                "enrich: AI enrichment unusable for %s, falling back to TF-IDF",
                article.id,
            )
        else:
            ai_error = None
        await tfidf_scoring.extract_and_store_keywords(session, article)
        used, method = tfidf_scoring, "tfidf"
    logger.info(
        "enrich[%s]: keywords stored via %s in %.2fs%s",
        article.id,
        method,
        time.perf_counter() - t0,
        f" (ai_error={ai_error})" if ai_error else "",
    )

    # 4. Per-user relevance score, frozen now (reads DB only, no LLM).
    # Use the same service that persisted keywords so the stored ``scorer``
    # indicator matches the real path (TF-IDF when AI fell back).
    t0 = time.perf_counter()
    await used.score_article_for_user(session, article.id, owner_id)
    logger.info(
        "enrich[%s]: relevance score computed in %.2fs",
        article.id,
        time.perf_counter() - t0,
    )

    # 5. Transition to enriched + record the active method/error (E7-S15).
    # ``enrichment_model`` is populated only on the AI success path (E10-S2);
    # TF-IDF fallback intentionally leaves it NULL so the debug panel doesn't
    # mislabel the row as AI-enriched.
    article.status = STATUS_ENRICHED
    article.enriched_at = datetime.now(timezone.utc)
    article.enrichment_method = method
    article.enrichment_error = ai_error
    article.enrichment_model = openrouter_model if method == "ai" else None


async def run() -> int:
    """CLI entry point: enrich one batch of pending articles.

    The refresh worker no longer calls this — it drives its own loop with
    ``pipeline_runs`` telemetry (E10-S1). Kept here so the cron script and
    direct ``python -m niouzou.crons.enrich`` invocations still work.
    """
    settings = get_settings()
    logger.info(
        "cron_enrich: start (batch_size=%d)", settings.enrich_batch_size
    )
    async with enrichment_resources() as resources:
        async with session_scope() as session:
            pending_ids = await _pending_article_ids(
                session, settings.enrich_batch_size
            )

        if not pending_ids:
            logger.info("cron_enrich: no pending articles — done")
            return 0

        logger.info("cron_enrich: %d articles to enrich", len(pending_ids))
        enriched = 0
        batch_start = time.perf_counter()
        for idx, article_id in enumerate(pending_ids, start=1):
            t0 = time.perf_counter()
            logger.info(
                "cron_enrich: [%d/%d] starting article %s",
                idx,
                len(pending_ids),
                article_id,
            )
            try:
                async with session_scope() as session:
                    article = await session.get(Article, article_id)
                    if article is None or article.status != STATUS_PENDING:
                        logger.info(
                            "cron_enrich: [%d/%d] skipped (already handled)",
                            idx,
                            len(pending_ids),
                        )
                        continue
                    await enrich_article(
                        session,
                        article,
                        enrichment=resources.enrichment,
                        ai_scoring=resources.ai_scoring,
                        tfidf_scoring=resources.tfidf_scoring,
                        openrouter_model=resources.openrouter_model,
                    )
                    enriched += 1
                logger.info(
                    "cron_enrich: [%d/%d] done in %.2fs",
                    idx,
                    len(pending_ids),
                    time.perf_counter() - t0,
                )
            except Exception:
                # Isolate failures: a bad article must not abort the batch.
                logger.exception(
                    "cron_enrich: [%d/%d] failed to enrich article %s",
                    idx,
                    len(pending_ids),
                    article_id,
                )

        logger.info(
            "cron_enrich: done — enriched %d/%d articles in %.1fs",
            enriched,
            len(pending_ids),
            time.perf_counter() - batch_start,
        )
        return enriched


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
