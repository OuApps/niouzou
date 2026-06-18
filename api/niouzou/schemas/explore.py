"""Explore schemas (E9-S3) — history + new tabs of the Explore screen."""

from datetime import datetime

from pydantic import BaseModel

from niouzou.schemas.feed import FeedArticle


class ExploreHistoryArticle(FeedArticle):
    """An article the user has already impressed; carries when it was seen."""

    seen_at: datetime


class ExploreHistoryResponse(BaseModel):
    articles: list[ExploreHistoryArticle]
    next_cursor: str | None
    has_more: bool


class ExploreNewResponse(BaseModel):
    """Same shape as the feed — articles enriched but not yet seen, ranked by
    gravity without the score-threshold / random-surface gates."""

    articles: list[FeedArticle]
    next_cursor: str | None
    has_more: bool


class ExploreSearchArticle(FeedArticle):
    """A text-search hit (E17-S3). Spans seen and unseen articles, so
    ``seen_at`` is present only when the user has already impressed it."""

    seen_at: datetime | None = None


class ExploreSearchResponse(BaseModel):
    articles: list[ExploreSearchArticle]
    next_cursor: str | None
    has_more: bool
