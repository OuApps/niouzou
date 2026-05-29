"""articles: per-source uniqueness on miniflux_entry_id (E7-S14)

Revision ID: 5d2a9f1c8b3e
Revises: 4c1f8a7b2d5e
Create Date: 2026-05-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "5d2a9f1c8b3e"
down_revision: Union[str, None] = "4c1f8a7b2d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Two users subscribed to the same RSS feed each get their own article row,
    # so miniflux_entry_id is no longer globally unique. The replacement key is
    # (source_id, miniflux_entry_id): a single user still can't ingest the same
    # entry twice, but distinct sources can share it.
    op.drop_constraint(
        "articles_miniflux_entry_id_key", "articles", type_="unique"
    )
    op.create_unique_constraint(
        "uq_articles_source_entry",
        "articles",
        ["source_id", "miniflux_entry_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_articles_source_entry", "articles", type_="unique")
    op.create_unique_constraint(
        "articles_miniflux_entry_id_key", "articles", ["miniflux_entry_id"]
    )
