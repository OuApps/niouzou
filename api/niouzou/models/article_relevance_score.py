import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base


class ArticleRelevanceScore(Base):
    __tablename__ = "article_relevance_scores"
    __table_args__ = (
        CheckConstraint(
            "relevance_score >= 0.0 AND relevance_score <= 1.0",
            name="ck_relevance_scores_range",
        ),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    scorer: Mapped[str | None] = mapped_column(String, nullable=True)
