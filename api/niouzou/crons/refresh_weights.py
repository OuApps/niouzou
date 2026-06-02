"""cron_refresh_weights — daily full recompute of keyword_weights (E3-S8).

Run with: ``uv run python -m niouzou.crons.refresh_weights``.

A safety net for the synchronous per-feedback recompute: it rebuilds every
user's weights from the full ``article_feedbacks`` history.

  * Idempotent — running twice yields identical rows.
  * Skips rows flagged ``manually_overridden`` (their weight is user-pinned).
  * ``article_relevance_scores.relevance_score`` is never recomputed —
    scores are frozen at enrichment time. The cron does flip the
    ``is_cold_start`` flag (E10-S4) on rows whose keywords have since
    gained a user weight.
"""

import asyncio
import logging

from niouzou.db import session_scope
from niouzou.services.weights import demote_cold_flags, recompute_all

logger = logging.getLogger("niouzou.cron_refresh_weights")


async def run() -> None:
    """Execute one full keyword-weight recompute across all users."""
    async with session_scope() as session:
        await recompute_all(session)
        demoted = await demote_cold_flags(session)
    logger.info(
        "cron_refresh_weights: recomputed all keyword weights "
        "(cold_demoted=%d)",
        demoted,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
