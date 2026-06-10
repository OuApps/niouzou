"""cron_refresh_weights — daily full recompute of keyword_weights (E3-S8).

Run with: ``uv run python -m niouzou.crons.refresh_weights``.

A safety net for the synchronous per-feedback recompute: it rebuilds every
user's weights from the full ``article_feedbacks`` history.

  * Idempotent — running twice yields identical rows.
  * Skips rows flagged ``manually_overridden`` (their weight is user-pinned).
  * In classic mode, ``article_relevance_scores.relevance_score`` is never
    recomputed — scores are frozen at enrichment. The cron does flip the
    ``is_cold_start`` flag (E10-S4) on rows whose keywords have since
    gained a user weight.
  * E16-S3 — in smart mode only, a nightly rescoring pass recomputes the
    relevance scores of recently ingested articles, so the feed benefits
    retroactively from new feedback (the frozen-score fix). Older rows stay
    frozen: gravity has already pushed them out of the feed.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.db import session_scope
from niouzou.models import Article, ArticleRelevanceScore
from niouzou.scoring import ScoringPipeline, TFIDFScorer
from niouzou.scoring.smart_match import SmartMatchParams
from niouzou.services.scoring_service import ScoringService
from niouzou.services.settings_service import SettingsService
from niouzou.services.weights import demote_cold_flags, recompute_all

logger = logging.getLogger("niouzou.cron_refresh_weights")


async def rescore_recent_smart(session: AsyncSession) -> int:
    """Re-score recent articles' relevance rows — smart mode only (E16-S3).

    No-op (returns 0) when ``scoring_mode = 'classic'``: Classic scores stay
    frozen at enrichment, exactly as before E16. In smart mode, every
    ``article_relevance_scores`` row whose article was ingested within the
    last ``smart_rescore_window_days`` is recomputed through the same entry
    point as enrichment-time scoring (``score_article_for_user``), so
    articles without an embedding transparently fall back to the active
    Classic scorer. Returns the number of rows rescored.
    """
    effective = await SettingsService(session).get_effective()
    if effective.scoring_mode != "smart":
        return 0

    if effective.openrouter_api_key:
        from niouzou.scoring.ai_keyword import AIKeywordScorer

        # No client: the relevance fallback path only uses the pure
        # ``score()`` maths, never the LLM — the name stamp must just match
        # the engine an enrichment-time fallback would have used.
        fallback_pipeline = ScoringPipeline(AIKeywordScorer())
    else:
        fallback_pipeline = ScoringPipeline(TFIDFScorer())

    scoring = ScoringService(
        fallback_pipeline,
        max_keywords_per_article=effective.max_keywords_per_article,
        scoring_mode="smart",
        smart_params=SmartMatchParams(
            topk=effective.smart_topk,
            lambda_=effective.smart_lambda,
            beta=effective.smart_beta,
            decay_halflife_days=effective.smart_decay_halflife_days,
        ),
    )

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=effective.smart_rescore_window_days
    )
    pairs = (
        await session.execute(
            select(ArticleRelevanceScore.article_id, ArticleRelevanceScore.user_id)
            .join(Article, Article.id == ArticleRelevanceScore.article_id)
            .where(Article.created_at > cutoff)
        )
    ).all()

    for article_id, user_id in pairs:
        await scoring.score_article_for_user(session, article_id, user_id)
    return len(pairs)


async def run() -> None:
    """Execute one full keyword-weight recompute across all users."""
    async with session_scope() as session:
        await recompute_all(session)
        demoted = await demote_cold_flags(session)
        rescored = await rescore_recent_smart(session)
    logger.info(
        "cron_refresh_weights: recomputed all keyword weights "
        "(cold_demoted=%d, smart_rescored=%d)",
        demoted,
        rescored,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
