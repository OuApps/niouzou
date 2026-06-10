import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base

STATUS_PENDING = "pending"
# Transient status set by the refresh worker just before enrichment begins
# on a given article (E10-S1). Committed in its own short transaction so
# /stats can show in-progress counts without polling, and so a worker crash
# leaves a recoverable marker that the startup reaper rolls back to pending.
STATUS_ENRICHING = "enriching"
STATUS_ENRICHED = "enriched"


class Article(Base):
    __tablename__ = "articles"
    # Per-user dedup: the same Miniflux entry produces one article row per
    # subscribing Source (each user sees and feedbacks their own copy).
    __table_args__ = (
        UniqueConstraint(
            "source_id", "miniflux_entry_id", name="uq_articles_source_entry"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    miniflux_entry_id: Mapped[int] = mapped_column(nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_executive: Mapped[str | None] = mapped_column(Text, nullable=True)
    og_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String, server_default=text("'pending'"), nullable=False
    )
    enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    enrichment_method: Mapped[str | None] = mapped_column(String, nullable=True)
    enrichment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # E10-S2 — OpenRouter model id used for the successful AI enrichment, e.g.
    # ``"google/gemma-4-28b"``. NULL on the TF-IDF path (native or fallback) —
    # ``enrichment_method='tfidf'`` already signals that case so the column is
    # left blank rather than duplicating the indicator.
    enrichment_model: Mapped[str | None] = mapped_column(String, nullable=True)
    # E16 — semantic embedding of title + summary_executive (Qwen3-Embedding,
    # L2-normalised, document mode without instruction prefix). NULL until the
    # enrichment cron or the backfill CLI computes it; Smart Match falls back
    # to the Classic scorer for NULL rows.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
