"""Split article_feedbacks.action into reaction / is_saved / read_full_article (E9-S1).

Destructive migration: skip rows are deleted (they were never consumed by
scoring), the ``action`` column and its check constraint are dropped, and
three new columns replace it. No useful downgrade — a Postgres backup is
recommended before running this.

Revision ID: 9b1c4f7a2e08
Revises: 8f5d2e9c1a4b
Create Date: 2026-05-31 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9b1c4f7a2e08"
down_revision: Union[str, None] = "8f5d2e9c1a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop skip rows up front. They produced (none, false, false), which is
    #    indistinguishable from "no feedback row at all" but would inflate
    #    saved_count / impression-derived metrics if left behind.
    op.execute(
        "DELETE FROM article_feedbacks WHERE action = 'skip'"
    )

    # 2. Add the new columns with NOT NULL defaults so existing rows get a
    #    valid state immediately. The defaults stay in place so future inserts
    #    that omit a column get the same treatment.
    op.add_column(
        "article_feedbacks",
        sa.Column(
            "reaction",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )
    op.add_column(
        "article_feedbacks",
        sa.Column(
            "is_saved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "article_feedbacks",
        sa.Column(
            "read_full_article",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 3. Backfill from the legacy `action` column.
    #    like → reaction='like'
    #    dislike → reaction='dislike'
    #    save → is_saved=true (reaction stays 'none')
    op.execute(
        """
        UPDATE article_feedbacks
        SET reaction = CASE
                WHEN action = 'like' THEN 'like'
                WHEN action = 'dislike' THEN 'dislike'
                ELSE 'none'
            END,
            is_saved = (action = 'save')
        """
    )

    # 4. Drop the legacy check constraint, then the column.
    op.drop_constraint(
        "ck_feedbacks_action", "article_feedbacks", type_="check"
    )
    op.drop_column("article_feedbacks", "action")

    # 5. Constrain the new reaction column.
    op.create_check_constraint(
        "ck_feedbacks_reaction",
        "article_feedbacks",
        "reaction IN ('like', 'dislike', 'none')",
    )


def downgrade() -> None:
    # No useful downgrade — skipped rows are gone and we can't disambiguate
    # like+save from save+like in the legacy single-action world. Restore from
    # a Postgres backup if you need to roll back.
    raise NotImplementedError(
        "E9-S1 is a destructive migration with no automated downgrade. "
        "Restore from a Postgres backup."
    )
