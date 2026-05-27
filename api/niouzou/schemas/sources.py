"""Source schemas (GET/POST /sources)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class SourceCreate(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _must_be_http(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    created_at: datetime


class SourcesListResponse(BaseModel):
    sources: list[SourceOut]
