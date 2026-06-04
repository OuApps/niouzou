import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base


class KeywordWeight(Base):
    __tablename__ = "keyword_weights"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    term: Mapped[str] = mapped_column(Text, primary_key=True)
    weight: Mapped[float] = mapped_column(
        Float, server_default=text("0.0"), nullable=False
    )
    like_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    dislike_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    manually_overridden: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
