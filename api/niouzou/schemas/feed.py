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
