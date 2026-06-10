"""Backfill ``articles.embedding`` for rows created before E16 (E16-S2).

Run with: ``uv run python -m niouzou.tools.backfill_embeddings``
(requires the ``embeddings`` extra: ``uv sync --extra embeddings``).

Embeds every article with ``embedding IS NULL`` in batches of 50, newest
first (recent articles are the ones Smart Match scores, so they pay off
immediately). Each batch commits in its own transaction, and the work query
is "embedding IS NULL" itself — interrupting and re-running resumes where it
left off, and a second run over a complete corpus does zero work. Pending
(not yet enriched) rows get a preliminary content-based vector that the
enrichment cron overwrites with the summary-based one.
"""

import asyncio
import logging
import time

from sqlalchemy import select

from niouzou.db import session_scope
from niouzou.models import Article
from niouzou.services.embedding_service import (
    EmbeddingService,
    build_article_text,
    embedding_available,
    get_embedding_service,
)

logger = logging.getLogger("niouzou.backfill_embeddings")

BATCH_SIZE = 50


async def run(
    *, batch_size: int = BATCH_SIZE, embedder: EmbeddingService | None = None
) -> int:
    """Embed all NULL-embedding articles; returns how many were embedded."""
    if embedder is None:
        if not embedding_available():
            raise SystemExit(
                "sentence-transformers is not installed — run "
                "`uv sync --extra embeddings` first"
            )
        embedder = get_embedding_service()

    total = 0
    while True:
        async with session_scope() as session:
            articles = (
                (
                    await session.execute(
                        select(Article)
                        .where(Article.embedding.is_(None))
                        .order_by(Article.created_at.desc())
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not articles:
                break

            t0 = time.perf_counter()
            texts = [
                build_article_text(a.title, a.summary_executive, a.content)
                for a in articles
            ]
            vectors = await asyncio.to_thread(embedder.embed_texts, texts)
            for article, vector in zip(articles, vectors):
                article.embedding = vector
            total += len(articles)
            logger.info(
                "backfill: embedded %d article(s) in %.1fs (total %d)",
                len(articles),
                time.perf_counter() - t0,
                total,
            )

    logger.info("backfill: done — %d article(s) embedded", total)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
