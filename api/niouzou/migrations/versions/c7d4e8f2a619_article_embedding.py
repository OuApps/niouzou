"""pgvector extension + ``articles.embedding`` column (E16-S1).

Smart Match (Epic 16) scores articles by semantic similarity, which needs
one 1024-dim vector per article (Qwen3-Embedding-0.6B, L2-normalised).
The column is nullable: articles enriched before the embedding service
existed stay NULL until the backfill CLI (E16-S2) processes them, and the
scorer falls back to Classic for them (E16-S3).

The downgrade drops the column but keeps the extension installed — other
objects could depend on it and ``CREATE EXTENSION IF NOT EXISTS`` makes
the upgrade idempotent anyway.

Revision ID: c7d4e8f2a619
Revises: bbc2d4e5f6a7
Create Date: 2026-06-10 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "c7d4e8f2a619"
down_revision: Union[str, None] = "bbc2d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("articles", sa.Column("embedding", Vector(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "embedding")
