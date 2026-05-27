"""Keyword weight schemas (GET /keywords, PATCH /keywords/{term})."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KeywordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    term: str
    weight: float
    like_count: int
    dislike_count: int
    updated_at: datetime


class KeywordsResponse(BaseModel):
    keywords: list[KeywordOut]
    next_cursor: str | None
    has_more: bool


class KeywordPatch(BaseModel):
    weight: float
