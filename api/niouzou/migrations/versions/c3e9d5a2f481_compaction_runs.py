"""Keyword-compaction run telemetry (E10-S3).

Adds ``compaction_runs`` so the keyword-compaction flow can record each
proposed merge ("preview") and whether it was applied, rejected, or failed.

Compaction merges semantically-equivalent terms ("FC Barcelone" + "Barça"
+ "Barcelona FC" → one canonical term) so per-user weights don't fragment
across spelling variants. The flow is preview → admin confirmation →
apply; both phases write rows here so the admin panel can resume an
abandoned preview.

Revision ID: c3e9d5a2f481
Revises: b12c8d4f6a93
Create Date: 2026-06-01 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e9d5a2f481"
down_revision: Union[str, None] = "b12c8d4f6a93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compaction_runs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "groups_json",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "keywords_merged",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('preview', 'applied', 'rejected', 'failed')",
            name="ck_compaction_runs_status",
        ),
    )
    # Latest preview / latest applied are looked up by the admin panel; the
    # query always orders by created_at DESC.
    op.create_index(
        "ix_compaction_runs_created_at",
        "compaction_runs",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_compaction_runs_created_at", table_name="compaction_runs")
    op.drop_table("compaction_runs")
