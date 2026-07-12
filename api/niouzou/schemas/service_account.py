"""Service account key schemas (E22-S2) — admin CRUD over MCP keys."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ServiceAccountKeyCreate(BaseModel):
    """Body for POST /admin/mcp-keys."""

    name: str = Field(min_length=1, max_length=100)


class ServiceAccountKeyOut(BaseModel):
    """A key as listed in the admin panel — never carries the raw token."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ServiceAccountKeyCreated(ServiceAccountKeyOut):
    """The create response — the only time the raw ``token`` is ever returned."""

    token: str
