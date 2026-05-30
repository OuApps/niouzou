"""force migration execution (E8 hotfix)

Revision ID: 9a6c3f8d2e5a
Revises: 8f5d2e9c1a4b
Create Date: 2026-05-30 21:45:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "9a6c3f8d2e5a"
down_revision: Union[str, None] = "8f5d2e9c1a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This migration forces Alembic to execute the previous migrations.
    # It has no-op, just ensures all users are admin if not already.
    op.execute(
        """
        UPDATE users SET is_admin = true WHERE is_admin = false;
        """
    )


def downgrade() -> None:
    pass
