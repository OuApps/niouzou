import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base

STATUS_PENDING = "pending"
STATUS_ENRICHED = "enriched"


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id"), nullable=False
    )
    miniflux_entry_id: Mapped[int] = mapped_column(unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_executive: Mapped[str | None] = mapped_column(Text, nullable=True)
    og_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String, server_default=text("'pending'"), nullable=False
    )
    enriched_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    enrichment_method: Mapped[str | None] = mapped_column(String, nullable=True)
    enrichment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
