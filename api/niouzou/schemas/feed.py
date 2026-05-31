"""Feed schemas (GET /feed). Also reused by GET /saved."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from niouzou.schemas.feedback import Reaction


class SourceRef(BaseModel):
    id: uuid.UUID
    name: str


class FeedArticle(BaseModel):
    id: uuid.UUID
    title: str
    summary_short: str | None
    # E9-S2 — bullet-point exec summary (AI-only) and the full crawled article
    # are now exposed inline so the fullscreen slide can render them without an
    # extra round-trip via the now-gone GET /articles/{id}.
    summary_executive: str | None = None
    content: str | None = None
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
    # Feedback state (E9-S1). Defaults applied when the user has not
    # interacted with the article yet.
    reaction: Reaction = "none"
    is_saved: bool = False
    read_full_article: bool = False


class FeedResponse(BaseModel):
    articles: list[FeedArticle]
    next_cursor: str | None
    has_more: bool
    # True while the user has fewer than COLD_START_THRESHOLD feedbacks (E7-S6):
    # the score threshold is bypassed so the feed isn't empty on day one. PWA
    # can use this to show a "keep swiping to personalise" hint.
    cold_start: bool = False


class SavedArticle(FeedArticle):
    saved_at: datetime


class SavedResponse(BaseModel):
    articles: list[SavedArticle]
    next_cursor: str | None
    has_more: bool
