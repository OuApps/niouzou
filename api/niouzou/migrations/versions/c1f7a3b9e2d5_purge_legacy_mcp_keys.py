"""Purge legacy MCP service account keys (E23-S1)

Revision ID: c1f7a3b9e2d5
Revises: b7e1a4c9f2d0
Create Date: 2026-07-14 12:00:00.000000

The E22 keys were minted under the "a key acts in its creator's context" model.
E23-S1 turned the MCP into its own identity (whole-base, score-free), so those
keys now grant a materially different scope than what they were issued for.
Delete every existing key to force admins to regenerate under the new model.

Data-only + irreversible: only the token hashes were ever stored, so a
downgrade cannot restore the rows — it is a no-op.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c1f7a3b9e2d5"
down_revision: Union[str, None] = "b7e1a4c9f2d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wipe all rows; the table structure is unchanged.
    op.execute("DELETE FROM service_account_keys")


def downgrade() -> None:
    # Irreversible: the raw tokens are gone, so revoked keys can't be re-minted.
    pass
