"""Feedback business logic (E9-S1): partial upsert + weight recompute."""

import uuid

from sqlalchemy import select, text

from niouzou.deps import SessionDep
from niouzou.errors import not_found
from niouzou.models import Article, ArticleKeyword, Source
from niouzou.schemas.feedback import FeedbackRequest, FeedbackResponse
from niouzou.services.weights import recompute_for_terms


class FeedbackService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def record(
        self, user_id: uuid.UUID, request: FeedbackRequest
    ) -> FeedbackResponse:
        # The article must belong to one of the user's sources.
        owns = await self.session.scalar(
            select(Article.id)
            .join(Source, Source.id == Article.source_id)
            .where(Article.id == request.article_id, Source.user_id == user_id)
        )
        if owns is None:
            raise not_found("Article not found")

        # Partial upsert: missing fields fall back to existing row (or default
        # for first-time inserts). read_full_article is monotone — once true,
        # never false again — enforced by GREATEST(existing, :read).
        # `updated_at` only bumps when something actually changes.
        upsert = text(
            """
            INSERT INTO article_feedbacks
                (article_id, user_id, reaction, is_saved, read_full_article)
            VALUES (
                :article_id, :user_id,
                COALESCE(:reaction, 'none'),
                COALESCE(:is_saved, false),
                COALESCE(:read_full_article, false)
            )
            ON CONFLICT (article_id, user_id) DO UPDATE SET
                reaction = COALESCE(:reaction, article_feedbacks.reaction),
                is_saved = COALESCE(:is_saved, article_feedbacks.is_saved),
                read_full_article = (
                    article_feedbacks.read_full_article
                    OR COALESCE(:read_full_article, false)
                ),
                updated_at = CASE WHEN (
                    (:reaction IS NOT NULL
                        AND article_feedbacks.reaction IS DISTINCT FROM :reaction)
                    OR (:is_saved IS NOT NULL
                        AND article_feedbacks.is_saved IS DISTINCT FROM :is_saved)
                    OR (
                        COALESCE(:read_full_article, false) = true
                        AND article_feedbacks.read_full_article = false
                    )
                ) THEN now() ELSE article_feedbacks.updated_at END
            RETURNING reaction, is_saved, read_full_article, updated_at
            """
        )
        # The "monotone read" rule: clients sending `read_full_article: false`
        # never overwrite a previous `true`. The INSERT branch falls back to
        # the column default (false); the UPDATE branch OR-merges.
        read_value: bool | None = request.read_full_article
        if read_value is False:
            read_value = None
        params = {
            "article_id": request.article_id,
            "user_id": user_id,
            "reaction": request.reaction,
            "is_saved": request.is_saved,
            "read_full_article": read_value,
        }
        row = (await self.session.execute(upsert, params)).one()

        # Affected terms = the article's keywords; recompute their weights.
        terms = list(
            await self.session.scalars(
                select(ArticleKeyword.term).where(
                    ArticleKeyword.article_id == request.article_id
                )
            )
        )
        await recompute_for_terms(self.session, user_id, terms)

        return FeedbackResponse(
            article_id=request.article_id,
            reaction=row.reaction,
            is_saved=row.is_saved,
            read_full_article=row.read_full_article,
            updated_at=row.updated_at,
        )
