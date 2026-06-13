"""Re-enrich articles whose ``content`` is a paywall/CGU boilerplate (E10-S6).

Run with: ``uv run python -m niouzou.tools.backfill_boilerplate_content``
(add ``--all`` to process the whole corpus instead of just the last
``SMART_RESCORE_WINDOW_DAYS``).

Before E10-S6, paywalled sources (e.g. « Le Progrès ») had their real RSS
teaser thrown away: ``newspaper4k`` returned the site's RGPD/cookie footer as
a non-empty string, so the RSS fallback never fired and the junk footer was
stored as ``content`` (then summarised by the LLM, yielding a hallucinated
summary). This one-shot finds those rows and recovers them:

  1. Detect boilerplate ``content`` with ``EnrichmentService._is_boilerplate``.
  2. Pull the original RSS body back from Miniflux (``get_entry_content``) —
     ``article.content`` was overwritten, so the teaser only survives there.
  3. Re-run the normal enrichment (``enrich_article``) with that RSS body as
     the fallback: newspaper re-fetches, hits the same footer, the new
     detector trips, and the teaser becomes ``content`` (→ ``is_premium`` and a
     coherent summary). Keywords and the embedding are recomputed and the
     article is rescored for its owner.

Each article is handled in its own transaction; a failure (or a purged
Miniflux entry, or a teaser that is *itself* boilerplate) skips that row and
the batch continues. Re-running is safe: a recovered article no longer matches
``_is_boilerplate`` so it isn't touched twice.
"""

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from niouzou.config import get_settings
from niouzou.crons.enrich import enrich_article, enrichment_resources
from niouzou.db import session_scope
from niouzou.models import Article, ArticleKeyword
from niouzou.models.article import STATUS_ENRICHED, STATUS_PENDING
from niouzou.services.enrichment_service import _strip_html
from niouzou.services.miniflux_client import MinifluxClient
from niouzou.services.miniflux_bootstrap import get_miniflux_token

logger = logging.getLogger("niouzou.backfill_boilerplate")

SCAN_BATCH = 200


async def _candidate_ids(*, is_boilerplate, all_articles: bool) -> list:
    """Ids of enriched articles whose stored ``content`` is boilerplate.

    Scanned (and filtered in Python — ``_is_boilerplate`` isn't expressible in
    SQL) before any mutation, so processing doesn't shift a moving offset.
    """
    cutoff = None
    if not all_articles:
        window = get_settings().smart_rescore_window_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    ids: list = []
    offset = 0
    while True:
        async with session_scope() as session:
            stmt = (
                select(Article.id, Article.content)
                .where(
                    Article.status == STATUS_ENRICHED,
                    Article.content.is_not(None),
                )
                .order_by(Article.created_at.desc())
                .offset(offset)
                .limit(SCAN_BATCH)
            )
            if cutoff is not None:
                stmt = stmt.where(Article.created_at >= cutoff)
            rows = (await session.execute(stmt)).all()
        if not rows:
            break
        for article_id, content in rows:
            if content and is_boilerplate(content):
                ids.append(article_id)
        offset += len(rows)
    return ids


async def run(*, all_articles: bool = False) -> int:
    """Re-enrich every boilerplate-content article; returns how many recovered."""
    token = await get_miniflux_token()
    settings = get_settings()

    async with enrichment_resources() as resources:
        is_boilerplate = resources.enrichment._is_boilerplate
        ids = await _candidate_ids(
            is_boilerplate=is_boilerplate, all_articles=all_articles
        )
        logger.info(
            "backfill_boilerplate: %d boilerplate article(s) to recover", len(ids)
        )

        recovered = 0
        async with MinifluxClient(settings.miniflux_url, token) as miniflux:
            for idx, article_id in enumerate(ids, start=1):
                try:
                    async with session_scope() as session:
                        article = await session.get(Article, article_id)
                        if article is None or not (
                            article.content and is_boilerplate(article.content)
                        ):
                            continue  # already recovered or vanished

                        rss_raw = await miniflux.get_entry_content(
                            article.miniflux_entry_id
                        )
                        teaser = _strip_html(rss_raw)
                        if not teaser or is_boilerplate(teaser):
                            logger.warning(
                                "backfill_boilerplate: [%d/%d] no usable RSS body "
                                "for %s — skipping",
                                idx,
                                len(ids),
                                article_id,
                            )
                            continue

                        # Drop the keywords mined from the footer, then re-run the
                        # normal enrichment with the RSS body as the fallback.
                        await session.execute(
                            delete(ArticleKeyword).where(
                                ArticleKeyword.article_id == article.id
                            )
                        )
                        article.content = rss_raw
                        article.status = STATUS_PENDING
                        await enrich_article(
                            session,
                            article,
                            enrichment=resources.enrichment,
                            scoring=resources.scoring,
                            openrouter_model=resources.openrouter_model,
                            embedder=resources.embedder,
                        )
                        recovered += 1
                    logger.info(
                        "backfill_boilerplate: [%d/%d] recovered %s",
                        idx,
                        len(ids),
                        article_id,
                    )
                except Exception:
                    logger.exception(
                        "backfill_boilerplate: [%d/%d] failed for %s",
                        idx,
                        len(ids),
                        article_id,
                    )

    logger.info(
        "backfill_boilerplate: done — recovered %d/%d article(s)",
        recovered,
        len(ids),
    )
    return recovered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="process the whole corpus, not just the last SMART_RESCORE_WINDOW_DAYS",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run(all_articles=args.all))


if __name__ == "__main__":
    main()
