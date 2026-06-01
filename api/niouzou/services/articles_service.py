"""Article detail business logic (GET /articles/{id})."""

import uuid

from fastapi import status
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.errors import APIError, not_found
from niouzou.models import (
    Article,
    ArticleFeedback,
    ArticleKeyword,
    ArticleRelevanceScore,
    KeywordWeight,
    Source,
)
from niouzou.schemas.articles import (
    ArticleDetail,
    ArticleSourceRef,
    ScoreDebug,
    ScoreDebugKeyword,
)


class ArticlesService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID, article_id: uuid.UUID) -> ArticleDetail:
        keywords_subq = (
            select(
                func.array_agg(
                    aggregate_order_by(
                        ArticleKeyword.term,
                        ArticleKeyword.salience.desc(),
                        ArticleKeyword.term.asc(),
                    )
                )
            )
            .where(ArticleKeyword.article_id == Article.id)
            .correlate(Article)
            .scalar_subquery()
        )

        row = (
            await self.session.execute(
                select(
                    Article,
                    Source.id.label("source_id"),
                    Source.name.label("source_name"),
                    Source.url.label("source_url"),
                    ArticleRelevanceScore.relevance_score,
                    ArticleRelevanceScore.scorer,
                    func.coalesce(ArticleFeedback.reaction, "none").label("reaction"),
                    func.coalesce(ArticleFeedback.is_saved, False).label("is_saved"),
                    func.coalesce(
                        ArticleFeedback.read_full_article, False
                    ).label("read_full_article"),
                    keywords_subq.label("keywords"),
                )
                .join(Source, Source.id == Article.source_id)
                .outerjoin(
                    ArticleRelevanceScore,
                    and_(
                        ArticleRelevanceScore.article_id == Article.id,
                        ArticleRelevanceScore.user_id == user_id,
                    ),
                )
                .outerjoin(
                    ArticleFeedback,
                    and_(
                        ArticleFeedback.article_id == Article.id,
                        ArticleFeedback.user_id == user_id,
                    ),
                )
                .where(Article.id == article_id, Source.user_id == user_id)
            )
        ).first()

        if row is None:
            raise not_found("Article not found")

        article: Article = row.Article
        premium_max_chars = get_settings().premium_content_max_chars
        return ArticleDetail(
            id=article.id,
            title=article.title,
            url=article.url,
            summary_short=article.summary_short,
            summary_executive=article.summary_executive,
            og_image_url=article.og_image_url,
            source=ArticleSourceRef(
                id=row.source_id, name=row.source_name, url=row.source_url
            ),
            published_at=article.published_at,
            enriched_at=article.enriched_at,
            relevance_score=row.relevance_score,
            scorer=row.scorer,
            keywords=list(row.keywords or []),
            is_premium=(
                article.content is not None
                and len(article.content) < premium_max_chars
            ),
            reaction=row.reaction,
            is_saved=bool(row.is_saved),
            read_full_article=bool(row.read_full_article),
        )

    async def score_debug(
        self, user_id: uuid.UUID, article_id: uuid.UUID
    ) -> ScoreDebug:
        """Explain how the relevance score was computed for the current user.

        Cross-user lookup returns 403 — never expose another user's
        ``keyword_weights`` even if they happen to share the same article via
        Miniflux dedup (an article still belongs to exactly one source / user
        per E2-S3). The article is loaded join-less from ``sources.user_id``
        so the authorization check happens in the same round-trip.
        """
        # Ownership / existence check. Splitting 403 from 404 leaks information
        # — but only that the id exists somewhere, which is already implied by
        # any feed/explore listing. ``not_found`` keeps the surface uniform.
        owner_row = (
            await self.session.execute(
                select(Source.user_id, Article.enrichment_model)
                .join(Source, Source.id == Article.source_id)
                .where(Article.id == article_id)
            )
        ).first()
        if owner_row is None:
            raise not_found("Article not found")
        if owner_row.user_id != user_id:
            raise APIError(
                status.HTTP_403_FORBIDDEN,
                "forbidden",
                "Article not accessible",
            )

        relevance, scorer_name = (
            await self.session.execute(
                select(
                    ArticleRelevanceScore.relevance_score,
                    ArticleRelevanceScore.scorer,
                ).where(
                    ArticleRelevanceScore.article_id == article_id,
                    ArticleRelevanceScore.user_id == user_id,
                )
            )
        ).first() or (None, None)

        # Article keywords sorted by salience DESC so the panel reads top-down.
        terms_rows = (
            await self.session.execute(
                select(ArticleKeyword.term)
                .where(ArticleKeyword.article_id == article_id)
                .order_by(
                    ArticleKeyword.salience.desc(), ArticleKeyword.term.asc()
                )
            )
        ).scalars().all()

        weights_rows = (
            await self.session.execute(
                select(KeywordWeight.term, KeywordWeight.weight).where(
                    KeywordWeight.user_id == user_id,
                    KeywordWeight.term.in_(terms_rows),
                )
            )
        ).all() if terms_rows else []
        weights = {term: weight for term, weight in weights_rows}

        return ScoreDebug(
            relevance_score=relevance,
            scorer=scorer_name,
            enrichment_model=owner_row.enrichment_model,
            keywords=[
                ScoreDebugKeyword(term=term, weight=weights.get(term))
                for term in terms_rows
            ],
        )
