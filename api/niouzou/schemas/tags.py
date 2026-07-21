"""Tag schemas (E24 — GET/POST/PATCH/DELETE /tags, PUT /sources/{id}/tags)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from niouzou.models.tag import MAX_TAGS_PER_SOURCE

TAG_NAME_MAX_CHARS = 40


def _validate_name(v: str) -> str:
    v = v.strip()
    if not 1 <= len(v) <= TAG_NAME_MAX_CHARS:
        raise ValueError(
            f"name must be 1-{TAG_NAME_MAX_CHARS} characters after trimming"
        )
    return v


class TagRef(BaseModel):
    """Compact tag shape embedded in SourceOut (E24-S3)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    # Per-tag relevance threshold; None inherits the global SCORE_THRESHOLD.
    threshold: float | None = None
    # Number of ACTIVE sources carrying this tag, populated by TagsService.
    source_count: int = 0


class TagsListResponse(BaseModel):
    tags: list[TagOut]


class TagCreate(BaseModel):
    name: str
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _validate_name(v)


class TagUpdate(BaseModel):
    """PATCH body — an explicit ``threshold: null`` reverts to inheritance,
    so the service checks ``model_fields_set`` to tell "absent" from "null"."""

    name: str | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return None if v is None else _validate_name(v)


class SourceTagsUpdate(BaseModel):
    """PUT /sources/{id}/tags — set-semantics: the list IS the new state."""

    tag_ids: list[uuid.UUID] = Field(max_length=MAX_TAGS_PER_SOURCE)
