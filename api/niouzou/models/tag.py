import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base

# E24 — max tags attachable to a single source (PUT /sources/{id}/tags).
MAX_TAGS_PER_SOURCE = 20


class Tag(Base):
    """Per-user source tag (E24) — the Loupe's unit of selection.

    ``threshold`` is the tag's own relevance threshold applied by the Feed when
    the Loupe is active; NULL inherits the instance-wide SCORE_THRESHOLD. It is
    a per-user setting carried by this row — never by ``app_settings``.
    """

    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint(
            "threshold IS NULL OR (threshold >= 0.0 AND threshold <= 1.0)",
            name="ck_tags_threshold",
        ),
        # Case-insensitive uniqueness per user: "Rugby" and "rugby" collide.
        Index(
            "uq_tags_user_lower_name", "user_id", text("lower(name)"), unique=True
        ),
        Index("idx_tags_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class SourceTag(Base):
    """N–N link between a source and a tag (E24-S1).

    Sources are soft-deleted (``deleted_at``), so pausing a source never fires
    the CASCADE — the link survives, inert. The CASCADE serves DELETE /tags/{id}
    (clears the links) and a hard source purge.
    """

    __tablename__ = "source_tags"
    __table_args__ = (Index("idx_source_tags_tag_id", "tag_id"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
