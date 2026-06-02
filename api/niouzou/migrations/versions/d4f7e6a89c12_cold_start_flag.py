"""Cold-start flag on relevance scores (E10-S4).

Adds ``article_relevance_scores.is_cold_start BOOLEAN NOT NULL DEFAULT
FALSE``. A row is cold when none of the article's keywords has a matching
row in ``keyword_weights`` for the same user — the scorer's output for
those rows is the neutral ~0.5 baseline, not a real prediction. The feed
uses the flag to bypass ``score_threshold`` (otherwise new keywords
disappear behind a high threshold) and to render a ``New`` badge instead
of a misleading percentage.

The flag is stamped by ``ScoringService`` at enrichment time and demoted
to FALSE by the nightly ``cron_refresh_weights`` once at least one of the
article's keywords has acquired a user weight. Symmetric warm→cold
transitions are rare in practice (compaction E10-S3 only touches aliases
and never deletes pinned rows) and ignored intentionally.

No index: the column is projected by every ``ranked_query`` (already
filtered by ``ars.user_id``) and updated in bulk by the cron's WHERE
``is_cold_start = TRUE`` scan — both paths are fine without a dedicated
index.

Backfill is skipped here so the upgrade stays fast on a busy instance.
Existing rows keep ``is_cold_start = FALSE`` until they're re-scored
(re-enrichment / weight recompute), which is conservative: an existing
article that should be cold will simply show its existing percentage one
last time until the next nightly refresh corrects the flag.

Revision ID: d4f7e6a89c12
Revises: c3e9d5a2f481
Create Date: 2026-06-02 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f7e6a89c12"
down_revision: Union[str, None] = "c3e9d5a2f481"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "article_relevance_scores",
        sa.Column(
            "is_cold_start",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("article_relevance_scores", "is_cold_start")
