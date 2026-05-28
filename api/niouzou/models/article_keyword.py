import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base


class ArticleKeyword(Base):
    __tablename__ = "article_keywords"
    __table_args__ = (
        CheckConstraint(
            "salience >= 0.0 AND salience <= 1.0",
            name="ck_article_keywords_salience",
        ),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id"), primary_key=True
    )
    term: Mapped[str] = mapped_column(Text, primary_key=True)
    salience: Mapped[float] = mapped_column(Float, nullable=False)
