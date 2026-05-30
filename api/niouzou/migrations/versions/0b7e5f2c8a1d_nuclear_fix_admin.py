"""nuclear fix: ensure is_admin column exists and promote all users

Revision ID: 0b7e5f2c8a1d
Revises: 9a6c3f8d2e5a
Create Date: 2026-05-30 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0b7e5f2c8a1d"
down_revision: Union[str, None] = "9a6c3f8d2e5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_admin column if it doesn't exist
    try:
        op.add_column(
            "users",
            sa.Column(
                "is_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    except Exception:
        # Column already exists, that's fine
        pass

    # Promote all users to admin
    op.execute("UPDATE users SET is_admin = true;")


def downgrade() -> None:
    pass
