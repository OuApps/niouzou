"""cron_nightly_refresh — daily weights recompute + dual-score refresh.

Run with: ``uv run python -m niouzou.crons.nightly_refresh``.
(Renamed from ``refresh_weights`` in E16-S9 — the job now refreshes both
persisted scores, not just the keyword weights.)

A safety net for the synchronous per-feedback recompute: it rebuilds every
user's weights from the full ``article_feedbacks`` history, then re-scores
the recent window so both score columns track the fresh signal.

  * Idempotent — running twice yields identical rows.
  * Skips rows flagged ``manually_overridden`` (their weight is user-pinned).
  * ``demote_cold_flags`` (E10-S4) flips ``keyword_cold_start`` on rows whose
    keywords have since gained a user weight. The smart cold flag is
    feedback-based and handled by the rescore below.
  * E16-S9 — ``rescore_recent`` recomputes BOTH ``keyword_score`` and
    ``smart_score`` for articles ingested within the rescore window, whatever
    ``scoring_mode``: without it, ``keyword_score`` frozen at enrichment
    would diverge from the nightly-recomputed weights and the side-by-side
    comparison (E16-S10) would be skewed. Older rows stay frozen: gravity
    has already pushed them out of the feed.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.db import session_scope
from niouzou.models import Article, ArticleRelevanceScore
from niouzou.scoring import ScoringPipeline
from niouzou.scoring.smart_match import SmartMatchParams
from niouzou.services.scoring_service import ScoringService
from niouzou.services.settings_service import SettingsService
from niouzou.services.weights import demote_cold_flags, recompute_all

logger = logging.getLogger("niouzou.cron_nightly_refresh")


async def rescore_recent(session: AsyncSession) -> int:
    """Re-score recent articles' relevance rows — both methods (E16-S9).

    Every ``article_relevance_scores`` row whose article was ingested within
    the last ``smart_rescore_window_days`` is recomputed through the same
    entry point as enrichment-time scoring (``score_article_for_user``),
    refreshing ``keyword_score`` AND ``smart_score`` together whatever
    ``scoring_mode`` is. Returns the number of rows rescored.
    """
    effective = await SettingsService(session).get_effective()

    scoring = ScoringService(
        ScoringPipeline(),
        max_keywords_per_article=effective.max_keywords_per_article,
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
    """Execute one full nightly refresh: weights + cold flags + rescore."""
    async with session_scope() as session:
        await recompute_all(session)
        demoted = await demote_cold_flags(session)
        rescored = await rescore_recent(session)
    logger.info(
        "cron_nightly_refresh: recomputed all keyword weights "
        "(cold_demoted=%d, rescored=%d)",
        demoted,
        rescored,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
