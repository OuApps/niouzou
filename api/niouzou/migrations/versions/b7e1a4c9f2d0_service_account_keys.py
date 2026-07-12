"""service_account_keys table (E22-S1)

Revision ID: b7e1a4c9f2d0
Revises: a1c4e7f2b9d6
Create Date: 2026-07-12 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1a4c9f2d0"
down_revision: Union[str, None] = "a1c4e7f2b9d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_account_keys",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_service_account_keys_key_hash"),
    )
    op.create_index(
        "ix_service_account_keys_user_id",
        "service_account_keys",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_service_account_keys_user_id", table_name="service_account_keys"
    )
    op.drop_table("service_account_keys")
