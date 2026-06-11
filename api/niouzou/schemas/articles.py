"""Article detail schema (GET /articles/{id})."""

import uuid
from datetime import datetime
from typing import Literal

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
    # E16-S8/S9 — both persisted scores; null when the method had no input
    # for this article (or it hasn't been scored for this user yet).
    keyword_score: float | None = None
    keyword_cold_start: bool = False
    smart_score: float | None = None
    smart_cold_start: bool = False
    active_method: Literal["keyword", "smart"] = "keyword"
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


# E10-S2 — Debug shape for ``GET /articles/{id}/score-debug``. Explains how
# the scores were computed: the LLM model (if any), the user's weight on each
# of the article's keywords (keyword section), and the k-NN neighbourhood +
# pins (smart section). ``weight: null`` distinguishes "keyword known to the
# article but no row in the user's ``keyword_weights``" (rendered as a dash)
# from a numeric zero.
class ScoreDebugKeyword(BaseModel):
    term: str
    weight: float | None


# E16-S7 — smart breakdown. One feedbacked article in the candidate's
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
    # E16-S10 — both methods are always present so the panel can show the two
    # sections side by side, whatever the active mode.
    keyword_score: float | None
    keyword_cold_start: bool = False
    smart_score: float | None
    smart_cold_start: bool = False
    active_method: Literal["keyword", "smart"] = "keyword"
    enrichment_model: str | None
    keywords: list[ScoreDebugKeyword]
    # E16-S7 — recomputed at request time: may differ marginally from the
    # neighbours that produced the stored score if the user feedbacked since
    # (nightly rescore keeps the gap small). Empty when the article has no
    # embedding.
    liked_neighbors: list[ScoreDebugNeighbor] = []
    disliked_neighbors: list[ScoreDebugNeighbor] = []
    pins: list[ScoreDebugPin] = []
