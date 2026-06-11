"""Persisting scoring results: article keywords and per-user relevance scores.

This is the bridge between the pure ``ScoringPipeline`` and the database. The
enrichment cron (Epic 5) calls it after content extraction; the logic lives
here so it stays out of the cron and is independently testable.

E16-S8 — both scoring methods are computed together on every pass,
independently of ``scoring_mode``:

  * ``keyword_score`` — AI keywords × user weights through the pipeline,
    NULL when the article has no keywords (LLM unavailable at enrichment;
    the TF-IDF fallback is gone).
  * ``smart_score`` — embedding k-NN (scoring/smart_match.py), NULL when the
    article has no embedding.

Invariants from docs/ARCHITECTURE.md:
  * ``keyword.salience`` is article-level, written once.
  * Scores are user-level, stamped at enrichment and refreshed nightly within
    the rescore window by ``cron_nightly_refresh`` (E16-S9).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.config import get_settings
from niouzou.models import Article, ArticleKeyword, ArticleRelevanceScore, KeywordWeight
from niouzou.scoring import ScoredKeyword, ScoringPipeline
from niouzou.scoring.smart_match import SmartMatchParams, smart_score


class ScoringService:
    def __init__(
        self,
        pipeline: ScoringPipeline | None = None,
        *,
        max_keywords_per_article: int | None = None,
        smart_params: SmartMatchParams | None = None,
    ) -> None:
        self.pipeline = pipeline or ScoringPipeline()
        self.smart_params = smart_params
        # Cap applied at the persistence boundary so every keyword source goes
        # through the same gate (E7-S5). Defaults to the env-driven setting;
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
        accumulating duplicates. Only used outside the enrichment cron (the
        cron stores the combined LLM call's keywords via ``store_keywords``).
        """
        text = " ".join(filter(None, [article.title, article.content]))
        keywords = self.pipeline.extract_keywords(text)
        return await self.store_keywords(session, article, keywords)

    async def store_keywords(
        self,
        session: AsyncSession,
        article: Article,
        keywords: list[ScoredKeyword],
    ) -> list[ScoredKeyword]:
        """Persist a pre-extracted keyword set (idempotent).

        Used by the combined-LLM enrichment path where summaries and keywords
        come from a single call — bypasses the pipeline's extractor while
        keeping the same persistence semantics as ``extract_and_store_keywords``
        (cap + upsert on ``(article_id, term)``).
        """
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
    ) -> None:
        """Compute and persist BOTH scores for this (article, user) pair.

        Always computes both methods (E16-S8) — ``scoring_mode`` plays no role
        here; it only selects which column the feed reads (E16-S9). A method
        whose input is missing (no keywords / no embedding) stores NULL and is
        treated as cold downstream.
        """
        keyword_score, keyword_cold = await self._keyword_score(
            session, article_id, user_id
        )

        smart_result = await smart_score(
            session, article_id, user_id, params=self.smart_params
        )
        if smart_result is None:
            # No embedding (legacy row not backfilled, or embedder missing at
            # enrichment) — the smart method simply has no opinion.
            smart_value, smart_cold = None, False
        else:
            smart_value, smart_cold = smart_result

        await self._upsert_scores(
            session,
            article_id,
            user_id,
            keyword_score=keyword_score,
            keyword_cold_start=keyword_cold,
            smart_score=smart_value,
            smart_cold_start=smart_cold,
        )

    async def _keyword_score(
        self, session: AsyncSession, article_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[float | None, bool]:
        """(keyword_score, keyword_cold_start) — NULL score without keywords."""
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
        if not keywords:
            # LLM unavailable at enrichment → no keywords → the keyword method
            # has nothing to score (badge «–», E16-S8).
            return None, False

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

        # E10-S4 — cold ssi aucun keyword de l'article n'apparaît dans le
        # vocabulaire user. Sémantiquement plus strict que « somme des poids
        # nulle » : un keyword pinned à 0 par l'utilisateur compte comme un
        # signal et désactive le statut cold (le user a explicitement statué).
        # On réutilise le dict ``user_weights`` déjà chargé pour éviter une
        # requête supplémentaire dans le hot path d'enrichissement.
        is_cold_start = not any(kw.term in user_weights for kw in keywords)
        return score, is_cold_start

    @staticmethod
    async def _upsert_scores(
        session: AsyncSession,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        keyword_score: float | None,
        keyword_cold_start: bool,
        smart_score: float | None,
        smart_cold_start: bool,
    ) -> None:
        values = {
            "keyword_score": keyword_score,
            "keyword_cold_start": keyword_cold_start,
            "smart_score": smart_score,
            "smart_cold_start": smart_cold_start,
        }
        await session.execute(
            pg_insert(ArticleRelevanceScore)
            .values(article_id=article_id, user_id=user_id, **values)
            .on_conflict_do_update(
                index_elements=["article_id", "user_id"], set_=values
            )
        )
