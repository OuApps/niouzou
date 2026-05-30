"""cron_enrich — extract content, summarise, score pending articles (E5).

Run with: ``uv run python -m niouzou.crons.enrich`` (or via the cron container).

Per pending article:
  1. Extract clean content with newspaper4k, falling back to the RSS body.
  2. Summarise — LLM (summary_short + summary_executive) when AI is on, else a
     newspaper-derived summary_short.
  3. Extract + store keywords via ScoringService (the AI scorer when a key is
     set; on LLM failure, retry once then fall back to TF-IDF — E5-S2).
  4. Score the article for its source's owner and freeze the relevance_score.
  5. Mark the article ``enriched``.

Persistence and scoring maths are NOT reimplemented here — steps 3–4 delegate
to ScoringService (Epic 3). The cron only orchestrates and owns the article
status transition.

Per-user scoring scope (E5-S2 open item): an article belongs to exactly one
source, which belongs to exactly one user, and the feed only ever surfaces an
article to that source's owner. So we score for that single owner — who, by
construction, registered before the source existed. No backfill for "new users
on pre-existing articles" is needed in this single-owner model; it would only
matter if articles were shared across users (see E7-S6).

Each article is enriched in its own transaction so one failure can't roll back
a whole batch. Blocking network calls (newspaper, LLM) run off the event loop
via asyncio.to_thread.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.config import get_settings
from niouzou.db import session_scope
from niouzou.models import Article, Source
from niouzou.models.article import STATUS_ENRICHED, STATUS_PENDING
from niouzou.scoring import ScoringPipeline, TFIDFScorer
from niouzou.services.enrichment_service import EnrichmentService
from niouzou.services.openrouter_client import OpenRouterClient
from niouzou.services.scoring_service import ScoringService
from niouzou.services.settings_service import SettingsService

logger = logging.getLogger("niouzou.cron_enrich")


async def _pending_article_ids(session: AsyncSession, limit: int) -> list[uuid.UUID]:
    """Oldest pending article ids first (FIFO enrichment)."""
    rows = await session.execute(
        select(Article.id)
        .where(Article.status == STATUS_PENDING)
        .order_by(Article.created_at)
        .limit(limit)
    )
    return list(rows.scalars().all())


async def enrich_article(
    session: AsyncSession,
    article: Article,
    *,
    enrichment: EnrichmentService,
    ai_scoring: ScoringService,
    tfidf_scoring: ScoringService,
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
    article.status = STATUS_ENRICHED
    article.enriched_at = datetime.now(timezone.utc)
    article.enrichment_method = method
    article.enrichment_error = ai_error


async def run() -> int:
    """Enrich one batch of pending articles. Returns the number enriched."""
    settings = get_settings()
    # Resolve runtime overrides (E8-S2): the admin may have flipped the model
    # or pasted a fresh API key since the last run. Snapshot once per batch so
    # the rest of the pipeline sees a consistent view.
    async with session_scope() as cfg_session:
        effective = await SettingsService(cfg_session).get_effective()

    # One OpenRouter client, shared by summaries and keyword extraction (None
    # when no key — the AI path is then skipped entirely). Closed in finally so
    # the httpx connection pool isn't leaked.
    client = OpenRouterClient.from_overrides(
        effective.openrouter_api_key, effective.openrouter_model
    )
    enrichment = EnrichmentService(client)
    # Dependency-free fallback: used for scoring (DB-only maths) and whenever
    # the LLM keyword path fails or AI is off.
    tfidf_scoring = ScoringService(
        ScoringPipeline(TFIDFScorer()),
        max_keywords_per_article=effective.max_keywords_per_article,
    )
    if client is None:
        # Same object as the fallback so _store_keywords takes the direct path.
        ai_scoring = tfidf_scoring
    else:
        # Lazy import keeps the AI module off the no-key path.
        from niouzou.scoring.ai_keyword import AIKeywordScorer

        ai_scoring = ScoringService(
            ScoringPipeline(AIKeywordScorer(client)),
            max_keywords_per_article=effective.max_keywords_per_article,
        )

    logger.info(
        "cron_enrich: start (batch_size=%d, ai_enabled=%s, model=%s)",
        settings.enrich_batch_size,
        enrichment.ai_enabled,
        effective.openrouter_model if client is not None else "n/a",
    )
    try:
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
                        enrichment=enrichment,
                        ai_scoring=ai_scoring,
                        tfidf_scoring=tfidf_scoring,
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
            "cron_enrich: done — enriched %d/%d articles in %.1fs (ai=%s)",
            enriched,
            len(pending_ids),
            time.perf_counter() - batch_start,
            enrichment.ai_enabled,
        )
        return enriched
    finally:
        if client is not None:
            client.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
