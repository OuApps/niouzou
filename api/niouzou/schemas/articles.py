"""Article detail schema (GET /articles/{id})."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from niouzou.schemas.feedback import FeedbackAction


class ArticleSourceRef(BaseModel):
    id: uuid.UUID
    name: str
    url: str


class ArticleFeedbackInfo(BaseModel):
    action: FeedbackAction
    updated_at: datetime


class ArticleDetail(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    summary_short: str | None
    summary_executive: str | None
    og_image_url: str | None
    source: ArticleSourceRef
    published_at: datetime | None
    enriched_at: datetime | None
    # Null when the article has not been scored for this user yet.
    relevance_score: float | None
    # "tfidf" or "ai_keyword" when known, null for unscored / legacy rows.
    scorer: str | None = None
    feedback: ArticleFeedbackInfo | None
    # All keywords sorted by salience DESC (E7-S10). Empty list when unenriched.
    keywords: list[str] = []
    # True when the stored content is suspiciously short for an enriched
    # article — typically a paywall teaser (E7-S21).
    is_premium: bool = False
