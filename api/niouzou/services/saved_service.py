"""Saved-articles business logic (GET /saved).

Saved = articles whose feedback row has ``is_saved = true``, ordered by when
the feedback was last updated (descending), keyset-paginated. Restructured
in E9-S1 — the old ``action = 'save'`` predicate no longer exists.
"""

import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.models import (
    Article,
    ArticleFeedback,
    ArticleKeyword,
    ArticleRelevanceScore,
    Source,
)
from niouzou.pagination import decode_cursor, encode_cursor
from niouzou.schemas.feed import SavedArticle, SavedResponse, SourceRef
from niouzou.services.settings_service import SettingsService

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 50


class SavedService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def list_saved(
        self, user_id: uuid.UUID, cursor: str | None, limit: int | None
    ) -> SavedResponse:
        page_size = _clamp_limit(limit)
        premium_max_chars = get_settings().premium_content_max_chars

        # Returns NULL when the article has no keywords; coerced to [] in Python.
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

        # E16-S9 — both scores are returned; the active method tag follows
        # the live scoring_mode so the PWA highlights the right chip.
        scoring_mode = str(
            await SettingsService(self.session).get("scoring_mode")
        )

        stmt = (
            select(
                Article,
                Source.id.label("source_id"),
                Source.name.label("source_name"),
                ArticleRelevanceScore.keyword_score.label("keyword_score"),
                func.coalesce(
                    ArticleRelevanceScore.keyword_cold_start, False
                ).label("keyword_cold_start"),
                ArticleRelevanceScore.smart_score.label("smart_score"),
                func.coalesce(
                    ArticleRelevanceScore.smart_cold_start, False
                ).label("smart_cold_start"),
                ArticleFeedback.updated_at.label("saved_at"),
                ArticleFeedback.reaction.label("reaction"),
                ArticleFeedback.is_saved.label("is_saved"),
                ArticleFeedback.read_full_article.label("read_full_article"),
                keywords_subq.label("keywords"),
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
                ArticleFeedback.is_saved.is_(True),
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
                summary_executive=r.Article.summary_executive,
                content=r.Article.content,
                og_image_url=r.Article.og_image_url,
                url=r.Article.url,
                source=SourceRef(id=r.source_id, name=r.source_name),
                published_at=r.Article.published_at,
                keyword_score=r.keyword_score,
                keyword_cold_start=bool(r.keyword_cold_start),
                smart_score=r.smart_score,
                smart_cold_start=bool(r.smart_cold_start),
                active_method=scoring_mode,
                enrichment_model=r.Article.enrichment_model,
                saved_at=r.saved_at,
                keywords=list(r.keywords or []),
                is_premium=(
                    r.Article.content is not None
                    and len(r.Article.content) < premium_max_chars
                ),
                reaction=r.reaction,
                is_saved=r.is_saved,
                read_full_article=r.read_full_article,
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
