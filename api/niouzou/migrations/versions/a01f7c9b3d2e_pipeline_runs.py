"""Pipeline runs telemetry table (E10-S1).

Adds ``pipeline_runs`` so the refresh worker can record every fetch+enrich
cycle: when it ran, how long it took, how many articles it processed, and
whether it failed. ``/stats`` reads from this table to render the System
panel; without it the PWA can't distinguish "cron tick produced nothing"
(healthy) from "cron is stalled" (broken).

Also introduces ``'enriching'`` as a transient article status: each pending
article briefly flips to ``'enriching'`` before its enrichment transaction
commits ``'enriched'``. The transient status is what powers the in-progress
counter in ``/stats`` (no in-memory polling needed).

Revision ID: a01f7c9b3d2e
Revises: 9b1c4f7a2e08
Create Date: 2026-06-01 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a01f7c9b3d2e"
down_revision: Union[str, None] = "9b1c4f7a2e08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "articles_fetched", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "articles_enriched", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "articles_failed", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "articles_in_run", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("total_duration_s", sa.Float(), nullable=True),
        sa.Column("avg_s_per_article", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_pipeline_runs_status",
        ),
    )
    # /stats reads the most recent run; every query orders by started_at DESC.
    op.create_index(
        "ix_pipeline_runs_started_at",
        "pipeline_runs",
        [sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
