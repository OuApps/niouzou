"""Feed schemas (GET /feed). Also reused by GET /saved."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class SourceRef(BaseModel):
    id: uuid.UUID
    name: str


class FeedArticle(BaseModel):
    id: uuid.UUID
    title: str
    summary_short: str | None
    og_image_url: str | None
    url: str
    source: SourceRef
    published_at: datetime | None
    relevance_score: float
    # "tfidf" or "ai_keyword" when known, null for pre-E7-S7 rows.
    scorer: str | None = None
    # Top keywords sorted by salience DESC (E7-S10). Empty list when the article
    # has no extracted keywords yet (e.g. pending enrichment).
    keywords: list[str] = []
    # True when the stored content is suspiciously short for an enriched
    # article — typically a paywall teaser (E7-S21). Lets the PWA warn the
    # user before they tap through to a locked page.
    is_premium: bool = False


class FeedResponse(BaseModel):
    articles: list[FeedArticle]
    next_cursor: str | None
    has_more: bool


class SavedArticle(FeedArticle):
    saved_at: datetime


class SavedResponse(BaseModel):
    articles: list[SavedArticle]
    next_cursor: str | None
    has_more: bool
