"""Source schemas (GET/POST/PATCH /sources)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class SourceCreate(BaseModel):
    url: str
    fetch_full_content: bool = False

    @field_validator("url")
    @classmethod
    def _must_be_http(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class SourceUpdate(BaseModel):
    fetch_full_content: bool


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    created_at: datetime
    # State lives on the shared Miniflux feed, not on the Niouzou row —
    # populated by SourcesService rather than read from the ORM.
    fetch_full_content: bool = False


class SourcesListResponse(BaseModel):
    sources: list[SourceOut]
