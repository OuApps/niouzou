import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base

# Reaction values mirror the CHECK constraint defined below.
REACTION_LIKE = "like"
REACTION_DISLIKE = "dislike"
REACTION_NONE = "none"


class ArticleFeedback(Base):
    """User feedback on an article (E9-S1).

    The three dimensions are independent: a user can simultaneously dislike,
    save and read an article. ``reaction`` is bidirectional, ``is_saved`` is
    bidirectional, ``read_full_article`` is monotone (false → true only — the
    backend silently drops attempts to set it back to false).
    """

    __tablename__ = "article_feedbacks"
    __table_args__ = (
        CheckConstraint(
            "reaction IN ('like', 'dislike', 'none')",
            name="ck_feedbacks_reaction",
        ),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    reaction: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'none'")
    )
    is_saved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    read_full_article: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
