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

from niouzou.config import get_settings
from niouzou.models import Article, ArticleKeyword, ArticleRelevanceScore, KeywordWeight
from niouzou.scoring import ScoredKeyword, ScoringPipeline


class ScoringService:
    def __init__(
        self,
        pipeline: ScoringPipeline | None = None,
        *,
        max_keywords_per_article: int | None = None,
    ) -> None:
        self.pipeline = pipeline or ScoringPipeline()
        # Cap applied at the persistence boundary so it covers both TF-IDF and
        # AI extractors uniformly (E7-S5). Defaults to the env-driven setting;
        # tests override via the kwarg.
        self.max_keywords_per_article = (
            max_keywords_per_article
            if max_keywords_per_article is not None
            else get_settings().max_keywords_per_article
        )

    async def extract_and_store_keywords(
        self, session: AsyncSession, article: Article
    ) -> list[ScoredKeyword]:
        """Extract keywords from the article's text and store them (idempotent).

        Article-level and set once; re-running replaces them rather than
        accumulating duplicates.
        """
        text = " ".join(filter(None, [article.title, article.content]))
        keywords = self.pipeline.extract_keywords(text)
        # Top-N by salience; ties broken by the scorer's own ordering.
        keywords = sorted(keywords, key=lambda k: -k.salience)[
            : self.max_keywords_per_article
        ]
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

        scorer_name = self.pipeline.scorer_name
        await session.execute(
            pg_insert(ArticleRelevanceScore)
            .values(
                article_id=article_id,
                user_id=user_id,
                relevance_score=score,
                scorer=scorer_name,
            )
            .on_conflict_do_update(
                index_elements=["article_id", "user_id"],
                set_={"relevance_score": score, "scorer": scorer_name},
            )
        )
        return score
