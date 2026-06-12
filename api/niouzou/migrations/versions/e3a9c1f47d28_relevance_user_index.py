"""Recreate the user_id index on article_relevance_scores (E16-S8 follow-up).

``d8e2f5a91c47`` dropped ``relevance_score``, and Postgres silently dropped
``idx_relevance_scores_user_id (user_id, relevance_score DESC)`` along with
it — leaving the ``user_id`` FK unindexed (user-deletion CASCADE, per-user
maintenance passes). The PK ``(article_id, user_id)`` still covers the
ranked-query join, so this is a performance follow-up, not a correctness fix.

Shipped as a separate revision because ``d8e2f5a91c47`` had already run on
the production database when the gap was found — applied migrations are
frozen. ``IF NOT EXISTS`` keeps this idempotent on environments where the
index was recreated by hand during the investigation.

Revision ID: e3a9c1f47d28
Revises: d8e2f5a91c47
Create Date: 2026-06-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e3a9c1f47d28"
down_revision: Union[str, None] = "d8e2f5a91c47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_relevance_scores_user_id "
        "ON article_relevance_scores (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_relevance_scores_user_id")
