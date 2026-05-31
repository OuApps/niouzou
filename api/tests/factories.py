"""Small async helpers for seeding DB-backed tests."""

import itertools
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.models import (
    Article,
    ArticleKeyword,
    ArticleRelevanceScore,
    Source,
    User,
)
from niouzou.models.article import STATUS_ENRICHED
from niouzou.schemas.feedback import FeedbackRequest, Reaction

_entry_ids = itertools.count(1000)


async def make_user(session: AsyncSession, email: str = "u@test.dev") -> User:
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.flush()
    return user


async def make_source(
    session: AsyncSession, user: User, *, feed_id: int = 1, name: str = "Feed"
) -> Source:
    source = Source(
        user_id=user.id,
        miniflux_feed_id=feed_id,
        url=f"https://feed/{feed_id}",
        name=name,
    )
    session.add(source)
    await session.flush()
    return source


async def make_article(
    session: AsyncSession,
    source: Source,
    *,
    title: str = "Title",
    published_at: datetime | None = None,
    status: str = STATUS_ENRICHED,
) -> Article:
    article = Article(
        source_id=source.id,
        miniflux_entry_id=next(_entry_ids),
        url="https://example.com/a",
        title=title,
        status=status,
        published_at=published_at or datetime.now(timezone.utc),
    )
    session.add(article)
    await session.flush()
    return article


async def add_keyword(
    session: AsyncSession, article: Article, term: str, salience: float
) -> None:
    session.add(
        ArticleKeyword(article_id=article.id, term=term, salience=salience)
    )
    await session.flush()


async def set_relevance(
    session: AsyncSession, article: Article, user: User, score: float
) -> None:
    session.add(
        ArticleRelevanceScore(
            article_id=article.id, user_id=user.id, relevance_score=score
        )
    )
    await session.flush()


def feedback_request(
    article_id: uuid.UUID,
    *,
    reaction: Reaction | None = None,
    is_saved: bool | None = None,
    read_full_article: bool | None = None,
) -> FeedbackRequest:
    """Shorthand for building partial-update payloads in tests."""
    return FeedbackRequest(
        article_id=article_id,
        reaction=reaction,
        is_saved=is_saved,
        read_full_article=read_full_article,
    )
