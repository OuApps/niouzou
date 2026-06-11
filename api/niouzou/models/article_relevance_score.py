import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base


class ArticleRelevanceScore(Base):
    """Both scoring methods, persisted side by side (E16-S8).

    ``keyword_score`` and ``smart_score`` are computed together at enrichment
    (and refreshed nightly within the rescore window) regardless of
    ``scoring_mode`` — the mode only selects which column drives the feed
    filter + ranking (E16-S9). A NULL score means the method had nothing to
    work with for this article (no keywords ⇔ LLM unavailable at enrichment;
    no embedding ⇔ legacy row not backfilled) and is treated as cold by the
    ranked queries.
    """

    __tablename__ = "article_relevance_scores"
    __table_args__ = (
        CheckConstraint(
            "keyword_score IS NULL OR "
            "(keyword_score >= 0.0 AND keyword_score <= 1.0)",
            name="ck_keyword_score_range",
        ),
        CheckConstraint(
            "smart_score IS NULL OR (smart_score >= 0.0 AND smart_score <= 1.0)",
            name="ck_smart_score_range",
        ),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # AI keywords × user weights. NULL when the article has no keywords.
    keyword_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # TRUE when none of the article's keywords has a row in
    # ``keyword_weights`` for this user (E10-S4 semantics). Demoted nightly
    # by ``cron_nightly_refresh`` once a feedback brings a shared term into
    # the user's vocab.
    keyword_cold_start: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Embedding k-NN over the user's feedbacked articles (E16-S3 formula).
    # NULL when the article has no embedding.
    smart_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # TRUE when the user has no feedback with value > 0 (the smart-mode cold
    # definition). Refreshed by the nightly rescore, not by demote_cold_flags.
    smart_cold_start: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
