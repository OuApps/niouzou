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
from niouzou.services.openrouter_client import OpenRouterError
from niouzou.services.scoring_service import ScoringService

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


async def _store_keywords(
    session: AsyncSession,
    article: Article,
    *,
    ai_scoring: ScoringService,
    tfidf_scoring: ScoringService,
) -> None:
    """Extract + persist keywords, falling back to TF-IDF on any LLM failure.

    ``ai_scoring`` is the config-selected pipeline (AI when a key is set); its
    extractor already retries once internally, so a raised OpenRouterError here
    means the model is unusable — we then use the dependency-free TF-IDF path.
    """
    if ai_scoring is tfidf_scoring:
        await tfidf_scoring.extract_and_store_keywords(session, article)
        return
    try:
        await ai_scoring.extract_and_store_keywords(session, article)
    except OpenRouterError as exc:
        logger.warning(
            "enrich: AI keyword extraction failed for %s (%s), falling back to TF-IDF",
            article.id,
            exc,
        )
        await tfidf_scoring.extract_and_store_keywords(session, article)


async def enrich_article(
    session: AsyncSession,
    article: Article,
    *,
    enrichment: EnrichmentService,
    ai_scoring: ScoringService,
    tfidf_scoring: ScoringService,
) -> None:
    """Enrich a single article in the given (open) transaction."""
    owner_id = await session.scalar(
        select(Source.user_id).where(Source.id == article.source_id)
    )
    if owner_id is None:
        # Orphaned article (source deleted) — nothing to score for.
        logger.warning("enrich: no source owner for article %s, skipping", article.id)
        return

    # 1. Content extraction (blocking) off the event loop.
    extracted = await asyncio.to_thread(
        enrichment.extract_content, article.url, rss_fallback=article.content
    )
    if extracted.content:
        article.content = extracted.content
    if extracted.og_image_url and not article.og_image_url:
        article.og_image_url = extracted.og_image_url

    # 2. Summaries (LLM or fallback; never raises).
    summaries = await asyncio.to_thread(
        enrichment.generate_summaries, article.title, article.content
    )
    if not summaries.summary_short:
        summaries.summary_short = extracted.fallback_summary
    article.summary_short = summaries.summary_short
    article.summary_executive = summaries.summary_executive

    # 3. Keywords (AI with TF-IDF fallback) — persisted via ScoringService.
    await _store_keywords(
        session, article, ai_scoring=ai_scoring, tfidf_scoring=tfidf_scoring
    )

    # 4. Per-user relevance score, frozen now (reads DB only, no LLM).
    await tfidf_scoring.score_article_for_user(session, article.id, owner_id)

    # 5. Transition to enriched.
    article.status = STATUS_ENRICHED
    article.enriched_at = datetime.now(timezone.utc)


async def run() -> int:
    """Enrich one batch of pending articles. Returns the number enriched."""
    settings = get_settings()
    enrichment = EnrichmentService.from_settings()
    # AI pipeline when a key is set, else TF-IDF (ScoringPipeline picks).
    ai_scoring = ScoringService()
    # Dependency-free fallback used for scoring and on LLM failure.
    tfidf_scoring = ScoringService(ScoringPipeline(TFIDFScorer()))

    async with session_scope() as session:
        pending_ids = await _pending_article_ids(session, settings.enrich_batch_size)

    if not pending_ids:
        logger.info("cron_enrich: no pending articles")
        return 0

    enriched = 0
    for article_id in pending_ids:
        try:
            async with session_scope() as session:
                article = await session.get(Article, article_id)
                if article is None or article.status != STATUS_PENDING:
                    continue  # already handled by a concurrent/previous run
                await enrich_article(
                    session,
                    article,
                    enrichment=enrichment,
                    ai_scoring=ai_scoring,
                    tfidf_scoring=tfidf_scoring,
                )
                enriched += 1
        except Exception:
            # Isolate failures: a bad article must not abort the batch.
            logger.exception("cron_enrich: failed to enrich article %s", article_id)

    logger.info(
        "cron_enrich: enriched %d/%d pending articles (ai=%s)",
        enriched,
        len(pending_ids),
        enrichment.ai_enabled,
    )
    return enriched


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
