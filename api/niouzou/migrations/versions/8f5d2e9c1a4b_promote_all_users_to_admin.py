"""promote all users to admin

Revision ID: 8f5d2e9c1a4b
Revises: 7a4f1e9b0c12
Create Date: 2026-05-30 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "8f5d2e9c1a4b"
down_revision: Union[str, None] = "7a4f1e9b0c12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET is_admin = true;")


def downgrade() -> None:
    op.execute("UPDATE users SET is_admin = false;")
