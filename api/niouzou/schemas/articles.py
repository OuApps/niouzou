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


# E10-S2 — Debug shape for ``GET /articles/{id}/score-debug``. Explains how a
# relevance score was computed: the active scorer, the LLM model (if any),
# and the user's weight on each of the article's keywords. ``weight: null``
# distinguishes "keyword known to the article but no row in the user's
# ``keyword_weights``" (rendered as a dash) from a numeric zero.
class ScoreDebugKeyword(BaseModel):
    term: str
    weight: float | None


# E16-S7 — smart-mode breakdown. One feedbacked article in the candidate's
# k-NN neighbourhood: ``contribution = similarity × |value| × decay``.
class ScoreDebugNeighbor(BaseModel):
    title: str
    similarity: float
    value: float
    age_days: float
    contribution: float


class ScoreDebugPin(BaseModel):
    term: str
    weight: float
    salience: float
    contribution: float  # weight × salience, the term added inside the sigmoid


class ScoreDebug(BaseModel):
    relevance_score: float | None
    scorer: str | None
    enrichment_model: str | None
    keywords: list[ScoreDebugKeyword]
    # E16-S7 — populated only when ``scorer == 'smart_match'`` (null in
    # classic mode so the legacy payload is byte-identical). Recomputed at
    # request time: may differ marginally from the neighbours that produced
    # the stored score if the user feedbacked since (nightly rescore keeps
    # the gap small).
    liked_neighbors: list[ScoreDebugNeighbor] | None = None
    disliked_neighbors: list[ScoreDebugNeighbor] | None = None
    pins: list[ScoreDebugPin] | None = None
