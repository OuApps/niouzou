"""Saved-articles business logic (GET /saved).

Saved = articles whose latest feedback action is ``save``, ordered by when
they were saved (feedback.updated_at) descending, keyset-paginated.
"""

import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select

from niouzou.deps import SessionDep
from niouzou.models import (
    Article,
    ArticleFeedback,
    ArticleRelevanceScore,
    Source,
)
from niouzou.pagination import decode_cursor, encode_cursor
from niouzou.schemas.feed import SavedArticle, SavedResponse, SourceRef

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 50


class SavedService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def list_saved(
        self, user_id: uuid.UUID, cursor: str | None, limit: int | None
    ) -> SavedResponse:
        page_size = _clamp_limit(limit)

        stmt = (
            select(
                Article,
                Source.id.label("source_id"),
                Source.name.label("source_name"),
                func.coalesce(ArticleRelevanceScore.relevance_score, 0.0).label(
                    "relevance_score"
                ),
                ArticleFeedback.updated_at.label("saved_at"),
            )
            .join(ArticleFeedback, ArticleFeedback.article_id == Article.id)
            .join(Source, Source.id == Article.source_id)
            .outerjoin(
                ArticleRelevanceScore,
                and_(
                    ArticleRelevanceScore.article_id == Article.id,
                    ArticleRelevanceScore.user_id == user_id,
                ),
            )
            .where(
                ArticleFeedback.user_id == user_id,
                ArticleFeedback.action == "save",
            )
            .order_by(ArticleFeedback.updated_at.desc(), Article.id.desc())
            .limit(page_size + 1)
        )

        if cursor:
            decoded = decode_cursor(cursor)
            ts = datetime.fromisoformat(str(decoded["saved_at"]))
            last_id = uuid.UUID(str(decoded["id"]))
            # Keyset for ORDER BY (updated_at DESC, id DESC).
            stmt = stmt.where(
                or_(
                    ArticleFeedback.updated_at < ts,
                    and_(
                        ArticleFeedback.updated_at == ts, Article.id < last_id
                    ),
                )
            )

        rows = (await self.session.execute(stmt)).all()
        has_more = len(rows) > page_size
        rows = rows[:page_size]

        articles = [
            SavedArticle(
                id=r.Article.id,
                title=r.Article.title,
                summary_short=r.Article.summary_short,
                og_image_url=r.Article.og_image_url,
                url=r.Article.url,
                source=SourceRef(id=r.source_id, name=r.source_name),
                published_at=r.Article.published_at,
                relevance_score=r.relevance_score,
                saved_at=r.saved_at,
            )
            for r in rows
        ]

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(
                {"saved_at": last.saved_at.isoformat(), "id": str(last.Article.id)}
            )

        return SavedResponse(
            articles=articles, next_cursor=next_cursor, has_more=has_more
        )


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(limit, _MAX_LIMIT))
