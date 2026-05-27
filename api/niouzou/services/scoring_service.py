"""Persisting scoring results: article keywords and per-user relevance scores.

This is the bridge between the pure ``ScoringPipeline`` and the database. The
enrichment cron (Epic 5) calls it after content extraction; the logic lives
here so it stays out of the cron and is independently testable.

Invariants from docs/ARCHITECTURE.md:
  * ``keyword.salience`` is article-level, written once.
  * ``relevance_score`` is user-level, frozen at enrichment, never recomputed.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.models import Article, ArticleKeyword, ArticleRelevanceScore, KeywordWeight
from niouzou.scoring import ScoredKeyword, ScoringPipeline


class ScoringService:
    def __init__(self, pipeline: ScoringPipeline | None = None) -> None:
        self.pipeline = pipeline or ScoringPipeline()

    async def extract_and_store_keywords(
        self, session: AsyncSession, article: Article
    ) -> list[ScoredKeyword]:
        """Extract keywords from the article's text and store them (idempotent).

        Article-level and set once; re-running replaces them rather than
        accumulating duplicates.
        """
        text = " ".join(filter(None, [article.title, article.content]))
        keywords = self.pipeline.extract_keywords(text)
        if not keywords:
            return []

        stmt = (
            pg_insert(ArticleKeyword)
            .values(
                [
                    {
                        "article_id": article.id,
                        "term": kw.term,
                        "salience": kw.salience,
                    }
                    for kw in keywords
                ]
            )
            .on_conflict_do_update(
                index_elements=["article_id", "term"],
                set_={"salience": pg_insert(ArticleKeyword).excluded.salience},
            )
        )
        await session.execute(stmt)
        return keywords

    async def score_article_for_user(
        self, session: AsyncSession, article_id: uuid.UUID, user_id: uuid.UUID
    ) -> float:
        """Compute and persist this user's relevance_score for the article.

        Reads the article's stored saliences and the user's keyword weights,
        runs the pipeline, and upserts ``article_relevance_scores``.
        """
        keywords = [
            ScoredKeyword(term=term, salience=salience)
            for term, salience in (
                await session.execute(
                    select(ArticleKeyword.term, ArticleKeyword.salience).where(
                        ArticleKeyword.article_id == article_id
                    )
                )
            ).all()
        ]
        user_weights = dict(
            (
                await session.execute(
                    select(KeywordWeight.term, KeywordWeight.weight).where(
                        KeywordWeight.user_id == user_id
                    )
                )
            ).all()
        )

        score = self.pipeline.relevance(keywords, user_weights)

        await session.execute(
            pg_insert(ArticleRelevanceScore)
            .values(article_id=article_id, user_id=user_id, relevance_score=score)
            .on_conflict_do_update(
                index_elements=["article_id", "user_id"],
                set_={"relevance_score": score},
            )
        )
        return score
