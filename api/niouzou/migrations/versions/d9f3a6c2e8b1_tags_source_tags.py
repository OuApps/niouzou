"""Tags + source_tags (E24-S1)

Revision ID: d9f3a6c2e8b1
Revises: c1f7a3b9e2d5
Create Date: 2026-07-21 12:00:00.000000

Per-user source tags for the Loupe (E24): ``tags`` carries the name and the
optional per-tag relevance threshold (NULL = inherit the global
SCORE_THRESHOLD); ``source_tags`` is the N-N link. Uniqueness of the name is
case-insensitive per user (functional index on lower(name)).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9f3a6c2e8b1"
down_revision: Union[str, None] = "c1f7a3b9e2d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "threshold IS NULL OR (threshold >= 0.0 AND threshold <= 1.0)",
            name="ck_tags_threshold",
        ),
    )
    op.create_index(
        "uq_tags_user_lower_name",
        "tags",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_index("idx_tags_user_id", "tags", ["user_id"])

    op.create_table(
        "source_tags",
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Uuid(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("idx_source_tags_tag_id", "source_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("idx_source_tags_tag_id", table_name="source_tags")
    op.drop_table("source_tags")
    op.drop_index("idx_tags_user_id", table_name="tags")
    op.drop_index("uq_tags_user_lower_name", table_name="tags")
    op.drop_table("tags")
