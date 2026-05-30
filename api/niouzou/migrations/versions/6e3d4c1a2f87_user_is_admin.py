"""users.is_admin (E8-S1)

Revision ID: 6e3d4c1a2f87
Revises: 5d2a9f1c8b3e
Create Date: 2026-05-30 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6e3d4c1a2f87"
down_revision: Union[str, None] = "5d2a9f1c8b3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
