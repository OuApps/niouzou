"""Article detail schema (GET /articles/{id})."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from niouzou.schemas.feedback import Reaction


class ArticleSourceRef(BaseModel):
    id: uuid.UUID
    name: str
    url: str


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
    # All keywords sorted by salience DESC (E7-S10). Empty list when unenriched.
    keywords: list[str] = []
    # True when the stored content is suspiciously short for an enriched
    # article — typically a paywall teaser (E7-S21).
    is_premium: bool = False
    # Feedback state (E9-S1). Defaults applied when the user has not
    # interacted with the article yet.
    reaction: Reaction = "none"
    is_saved: bool = False
    read_full_article: bool = False
