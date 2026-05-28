"""article_relevance_scores.scorer column (E7-S7)

Revision ID: 3b8c5e2a91f4
Revises: 2a1f4c9b7e30
Create Date: 2026-05-28 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b8c5e2a91f4"
down_revision: Union[str, None] = "2a1f4c9b7e30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: rows scored before this column existed won't carry an indicator.
    op.add_column(
        "article_relevance_scores",
        sa.Column("scorer", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("article_relevance_scores", "scorer")
