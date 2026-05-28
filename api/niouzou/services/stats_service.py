"""Stats aggregator (GET /stats, E7-S15).

All values come from existing tables — no extra storage. Counts are scoped to
the requesting user via the user→source→article ownership chain.
"""

import uuid

from sqlalchemy import case, func, select

from niouzou.deps import SessionDep
from niouzou.models import (
    Article,
    ArticleFeedback,  # noqa: F401  (kept for future enrichment stats)
    KeywordWeight,
    Source,
)
from niouzou.models.article import STATUS_ENRICHED
from niouzou.schemas.stats import (
    ArticlesStats,
    EnrichmentStats,
    KeywordsStats,
    SourcesStats,
    Stats,
)


class StatsService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> Stats:
        # ── Articles (scoped to user's sources, ignoring soft-deleted) ────
        article_join = (
            select(Article)
            .join(Source, Source.id == Article.source_id)
            .where(Source.user_id == user_id, Source.deleted_at.is_(None))
        ).subquery()

        articles_row = (
            await self.session.execute(
                select(
                    func.count().label("total"),
                    func.count(
                        case(
                            (article_join.c.status != STATUS_ENRICHED, 1)
                        )
                    ).label("pending"),
                    func.max(article_join.c.created_at).label("last_fetched_at"),
                    func.max(article_join.c.enriched_at).label("last_enriched_at"),
                    func.count(
                        case((article_join.c.enrichment_method == "ai", 1))
                    ).label("total_ai"),
                    func.count(
                        case((article_join.c.enrichment_method == "tfidf", 1))
                    ).label("total_tfidf"),
                    func.count(
                        case(
                            (
                                (article_join.c.enrichment_method == "tfidf")
                                & (article_join.c.enrichment_error.is_not(None)),
                                1,
                            )
                        )
                    ).label("total_tfidf_fallback"),
                ).select_from(article_join)
            )
        ).one()

        # ── Last enrichment error (most recent non-null) ───────────────────
        last_err_row = (
            await self.session.execute(
                select(
                    article_join.c.enrichment_error,
                    article_join.c.enriched_at,
                )
                .where(article_join.c.enrichment_error.is_not(None))
                .order_by(article_join.c.enriched_at.desc())
                .limit(1)
            )
        ).first()

        # ── Sources ────────────────────────────────────────────────────────
        sources_total = await self.session.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.user_id == user_id, Source.deleted_at.is_(None))
        )
        # "active" mirrors total today — no per-source disable flag yet. Kept
        # as a separate field in the response so the PWA contract doesn't
        # change when that distinction is introduced.
        sources_active = sources_total

        # ── Keywords ───────────────────────────────────────────────────────
        keywords_row = (
            await self.session.execute(
                select(
                    func.count().label("total"),
                    func.count(
                        case((KeywordWeight.manually_overridden.is_(True), 1))
                    ).label("overridden"),
                ).where(KeywordWeight.user_id == user_id)
            )
        ).one()

        return Stats(
            articles=ArticlesStats(
                total=articles_row.total or 0,
                pending_enrichment=articles_row.pending or 0,
                last_fetched_at=articles_row.last_fetched_at,
            ),
            sources=SourcesStats(
                total=sources_total or 0,
                active=sources_active or 0,
            ),
            keywords=KeywordsStats(
                total=keywords_row.total or 0,
                manually_overridden=keywords_row.overridden or 0,
            ),
            enrichment=EnrichmentStats(
                last_enriched_at=articles_row.last_enriched_at,
                total_ai=articles_row.total_ai or 0,
                total_tfidf=articles_row.total_tfidf or 0,
                total_tfidf_fallback=articles_row.total_tfidf_fallback or 0,
                last_error=last_err_row.enrichment_error if last_err_row else None,
                last_error_at=last_err_row.enriched_at if last_err_row else None,
            ),
        )
