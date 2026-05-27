"""epic 3 additions: sources.deleted_at, keyword_weights.manually_overridden

Revision ID: 2a1f4c9b7e30
Revises: 1286f25de7b8
Create Date: 2026-05-27 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a1f4c9b7e30"
down_revision: Union[str, None] = "1286f25de7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Soft delete for sources — articles keep their NOT NULL FK intact.
    op.add_column(
        "sources",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Manual weight overrides preserved across recomputes.
    op.add_column(
        "keyword_weights",
        sa.Column(
            "manually_overridden",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("keyword_weights", "manually_overridden")
    op.drop_column("sources", "deleted_at")
