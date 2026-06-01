"""Track which LLM model enriched each article (E10-S2).

Adds ``articles.enrichment_model`` — the OpenRouter model id (e.g.
``"google/gemma-4-28b"``) used for the successful AI enrichment. NULL when
the article went through the TF-IDF path (native or fallback);
``enrichment_method='tfidf'`` already signals that case.

The column powers the new ``GET /articles/{id}/score-debug`` panel that
explains how a relevance score was computed — model name + scorer + the
user's weight on each of the article's keywords.

Revision ID: b12c8d4f6a93
Revises: a01f7c9b3d2e
Create Date: 2026-06-01 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b12c8d4f6a93"
down_revision: Union[str, None] = "a01f7c9b3d2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("enrichment_model", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("articles", "enrichment_model")
