"""Keyword weight schemas (GET /keywords, PATCH /keywords/{term})."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KeywordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    term: str
    weight: float
    like_count: int
    dislike_count: int
    manually_overridden: bool
    updated_at: datetime


class KeywordsResponse(BaseModel):
    keywords: list[KeywordOut]
    next_cursor: str | None
    has_more: bool


class KeywordPatch(BaseModel):
    """Partial update for a keyword weight.

    - ``weight`` alone: pin the weight (sets ``manually_overridden = True``).
    - ``manually_overridden: false`` alone: clear the pin, keep the weight.
    - Both: caller-controlled override of pin state and weight.
    """

    weight: float | None = None
    manually_overridden: bool | None = None
