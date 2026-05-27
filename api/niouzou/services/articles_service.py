"""Article detail business logic (GET /articles/{id})."""

import uuid

from sqlalchemy import and_, select

from niouzou.deps import SessionDep
from niouzou.errors import not_found
from niouzou.models import Article, ArticleFeedback, ArticleRelevanceScore, Source
from niouzou.schemas.articles import (
    ArticleDetail,
    ArticleFeedbackInfo,
    ArticleSourceRef,
)


class ArticlesService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID, article_id: uuid.UUID) -> ArticleDetail:
        row = (
            await self.session.execute(
                select(
                    Article,
                    Source.id.label("source_id"),
                    Source.name.label("source_name"),
                    Source.url.label("source_url"),
                    ArticleRelevanceScore.relevance_score,
                    ArticleFeedback.action,
                    ArticleFeedback.updated_at.label("feedback_updated_at"),
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
        feedback = (
            ArticleFeedbackInfo(action=row.action, updated_at=row.feedback_updated_at)
            if row.action is not None
            else None
        )

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
            feedback=feedback,
        )
