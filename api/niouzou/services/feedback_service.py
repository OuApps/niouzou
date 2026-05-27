"""Feedback business logic: upsert feedback, then recompute affected weights."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from niouzou.deps import SessionDep
from niouzou.errors import not_found
from niouzou.models import Article, ArticleFeedback, ArticleKeyword, Source
from niouzou.schemas.feedback import FeedbackResponse
from niouzou.services.weights import recompute_for_terms


class FeedbackService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def record(
        self, user_id: uuid.UUID, article_id: uuid.UUID, action: str
    ) -> FeedbackResponse:
        # The article must belong to one of the user's sources.
        owns = await self.session.scalar(
            select(Article.id)
            .join(Source, Source.id == Article.source_id)
            .where(Article.id == article_id, Source.user_id == user_id)
        )
        if owns is None:
            raise not_found("Article not found")

        # Idempotent upsert — last action wins.
        updated_at = await self.session.scalar(
            pg_insert(ArticleFeedback)
            .values(article_id=article_id, user_id=user_id, action=action)
            .on_conflict_do_update(
                index_elements=["article_id", "user_id"],
                set_={"action": action, "updated_at": func.now()},
            )
            .returning(ArticleFeedback.updated_at)
        )

        # Affected terms = the article's keywords; recompute their weights.
        terms = list(
            await self.session.scalars(
                select(ArticleKeyword.term).where(
                    ArticleKeyword.article_id == article_id
                )
            )
        )
        await recompute_for_terms(self.session, user_id, terms)

        return FeedbackResponse(
            article_id=article_id, action=action, updated_at=updated_at
        )
