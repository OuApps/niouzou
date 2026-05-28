"""articles.enrichment_method + enrichment_error (E7-S15)

Revision ID: 4c1f8a7b2d5e
Revises: 3b8c5e2a91f4
Create Date: 2026-05-28 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c1f8a7b2d5e"
down_revision: Union[str, None] = "3b8c5e2a91f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 'ai' or 'tfidf' — written by cron_enrich after each article. Null for rows
    # enriched before this column existed.
    op.add_column(
        "articles",
        sa.Column("enrichment_method", sa.String(), nullable=True),
    )
    # Captured exception when AI failed and the cron fell back to TF-IDF; null
    # on success or when AI is off.
    op.add_column(
        "articles",
        sa.Column("enrichment_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("articles", "enrichment_error")
    op.drop_column("articles", "enrichment_method")
