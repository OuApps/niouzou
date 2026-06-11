"""Dual persisted scores: keyword_score ⊕ smart_score (E16-S8/S9).

Both scoring methods now coexist on every ``article_relevance_scores`` row,
computed together at enrichment regardless of ``scoring_mode`` — the mode is
demoted from "which engine runs" to "which persisted score drives the feed
filter + ranking" (E16-S9). Consequences carried by this migration:

* ``keyword_score`` (NULL when the article has no keywords — the keyword
  extraction is LLM-only now that the TF-IDF fallback is removed) and
  ``smart_score`` (NULL when the article has no embedding) replace the single
  ``relevance_score``, each with its own cold flag.
* ``scorer`` is dropped: with TF-IDF gone, the column identity *is* the
  method (keyword = AI keywords × weights, smart = embedding k-NN).
* Backfill maps the legacy single score onto the column matching its
  ``scorer`` stamp; the other method stays NULL (rendered as «–») until the
  nightly rescore fills it.
* ``app_settings`` housekeeping for E16-S9: the ``scoring_mode`` value
  ``'classic'`` becomes ``'keyword'`` and the ``cron_refresh_weights_hour``
  key becomes ``cron_nightly_refresh_hour`` (the cron now refreshes both
  scores, not just keyword weights).

Revision ID: d8e2f5a91c47
Revises: c7d4e8f2a619
Create Date: 2026-06-11 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e2f5a91c47"
down_revision: Union[str, None] = "c7d4e8f2a619"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "article_relevance_scores",
        sa.Column("keyword_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "article_relevance_scores",
        sa.Column(
            "keyword_cold_start",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "article_relevance_scores",
        sa.Column("smart_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "article_relevance_scores",
        sa.Column(
            "smart_cold_start",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "ck_keyword_score_range",
        "article_relevance_scores",
        "keyword_score IS NULL OR (keyword_score >= 0.0 AND keyword_score <= 1.0)",
    )
    op.create_check_constraint(
        "ck_smart_score_range",
        "article_relevance_scores",
        "smart_score IS NULL OR (smart_score >= 0.0 AND smart_score <= 1.0)",
    )

    # Backfill: the legacy single score lands on the column matching its
    # provenance stamp. Legacy rows with scorer IS NULL predate E7-S7 and were
    # all produced by the keyword pathway.
    op.execute(
        """
        UPDATE article_relevance_scores
        SET smart_score = relevance_score, smart_cold_start = is_cold_start
        WHERE scorer = 'smart_match'
        """
    )
    op.execute(
        """
        UPDATE article_relevance_scores
        SET keyword_score = relevance_score, keyword_cold_start = is_cold_start
        WHERE scorer IS DISTINCT FROM 'smart_match'
        """
    )

    op.drop_constraint(
        "ck_relevance_scores_range", "article_relevance_scores", type_="check"
    )
    op.drop_column("article_relevance_scores", "relevance_score")
    op.drop_column("article_relevance_scores", "scorer")
    op.drop_column("article_relevance_scores", "is_cold_start")

    # E16-S9 settings housekeeping (no-ops on rows that don't exist).
    op.execute(
        "UPDATE app_settings SET value = 'keyword' "
        "WHERE key = 'scoring_mode' AND value = 'classic'"
    )
    op.execute(
        "UPDATE app_settings SET key = 'cron_nightly_refresh_hour' "
        "WHERE key = 'cron_refresh_weights_hour'"
    )


def downgrade() -> None:
    # Lossy by construction: the legacy schema can only hold one score per
    # row. The smart score wins when present (it was the active engine when
    # both exist), mirroring the upgrade's provenance mapping.
    op.add_column(
        "article_relevance_scores",
        sa.Column(
            "relevance_score",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
    )
    op.add_column(
        "article_relevance_scores", sa.Column("scorer", sa.String(), nullable=True)
    )
    op.add_column(
        "article_relevance_scores",
        sa.Column(
            "is_cold_start",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        """
        UPDATE article_relevance_scores
        SET relevance_score = COALESCE(smart_score, keyword_score, 0.5),
            scorer = CASE
                WHEN smart_score IS NOT NULL THEN 'smart_match'
                WHEN keyword_score IS NOT NULL THEN 'ai_keyword'
                ELSE NULL
            END,
            is_cold_start = CASE
                WHEN smart_score IS NOT NULL THEN smart_cold_start
                ELSE keyword_cold_start
            END
        """
    )
    op.alter_column(
        "article_relevance_scores", "relevance_score", server_default=None
    )
    op.create_check_constraint(
        "ck_relevance_scores_range",
        "article_relevance_scores",
        "relevance_score >= 0.0 AND relevance_score <= 1.0",
    )

    op.drop_constraint(
        "ck_keyword_score_range", "article_relevance_scores", type_="check"
    )
    op.drop_constraint(
        "ck_smart_score_range", "article_relevance_scores", type_="check"
    )
    op.drop_column("article_relevance_scores", "smart_cold_start")
    op.drop_column("article_relevance_scores", "smart_score")
    op.drop_column("article_relevance_scores", "keyword_cold_start")
    op.drop_column("article_relevance_scores", "keyword_score")

    op.execute(
        "UPDATE app_settings SET value = 'classic' "
        "WHERE key = 'scoring_mode' AND value = 'keyword'"
    )
    op.execute(
        "UPDATE app_settings SET key = 'cron_refresh_weights_hour' "
        "WHERE key = 'cron_nightly_refresh_hour'"
    )
