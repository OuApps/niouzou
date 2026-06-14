"""LLM usage log table (E10-S7).

Adds ``llm_usage_log`` so the System panel can show the OpenRouter bill over
1h/6h/24h. One row per successful chat completion made by
``enrichment_resources`` (cron_enrich / refresh worker) — cost is read back
via OpenRouter's ``/generation`` endpoint right after the completion.

Revision ID: f4b8d2a91c63
Revises: e3a9c1f47d28
Create Date: 2026-06-14 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4b8d2a91c63"
down_revision: Union[str, None] = "e3a9c1f47d28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_log",
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
        sa.Column("model", sa.String(), nullable=False),
        sa.Column(
            "cost_usd", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # /stats sums cost_usd over recent windows — ordered by created_at.
    op.create_index(
        "ix_llm_usage_log_created_at",
        "llm_usage_log",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_usage_log_created_at", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")
