"""Source schemas (GET/POST/PATCH /sources)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class SourceCreate(BaseModel):
    url: str
    # New sources always crawl the full article — the UI no longer exposes a
    # toggle and pre-existing sources keep whatever value Miniflux already has.
    fetch_full_content: bool = True

    @field_validator("url")
    @classmethod
    def _must_be_http(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class SourceUpdate(BaseModel):
    fetch_full_content: bool | None = None
    # E13-S5: toggle the source between running (True) and paused (False).
    # Paused sources stay listed in /sources but their articles are hidden
    # from Feed/Explore until reactivated.
    active: bool | None = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    created_at: datetime
    # State lives on the shared Miniflux feed, not on the Niouzou row —
    # populated by SourcesService rather than read from the ORM.
    fetch_full_content: bool = False
    # E13-S5: derived from ``Source.deleted_at`` (None → active).
    active: bool = True
    # E17-S6 — article volume for this source (total + last 24h), populated by
    # SourcesService. Shown on the Manage Sources screen for active and paused
    # sources alike.
    article_count_total: int = 0
    article_count_24h: int = 0


class SourcesListResponse(BaseModel):
    sources: list[SourceOut]
