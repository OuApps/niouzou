import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, String, text
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
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    scorer: Mapped[str | None] = mapped_column(String, nullable=True)
    # E10-S4 — TRUE when none of the article's keywords has a row in
    # ``keyword_weights`` for this user. Stamped by ``ScoringService`` at
    # enrichment time and demoted nightly by ``cron_refresh_weights`` once
    # a feedback brings at least one keyword into the user's vocab. Used
    # by ``ranked_query`` to bypass ``score_threshold`` and by the PWA to
    # show ``New`` instead of a misleading 50 % badge.
    is_cold_start: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
