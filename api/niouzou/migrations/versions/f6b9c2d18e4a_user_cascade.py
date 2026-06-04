"""Hard delete a user (E13-S3).

Adds ``ON DELETE CASCADE`` to every FK that points at ``users.id`` so the
admin can wipe a user with a single ``DELETE FROM users`` and let
PostgreSQL fan out through the dependent rows.

Tables cascaded here:

* ``sources.user_id`` — and via the source-side cascade added in
  e5a8b1c4f9d2, the user's articles and per-article rows go with it.
* ``article_feedbacks.user_id``
* ``article_impressions.user_id``
* ``article_relevance_scores.user_id``
* ``keyword_weights.user_id``

Revision ID: f6b9c2d18e4a
Revises: e5a8b1c4f9d2
Create Date: 2026-06-04 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f6b9c2d18e4a"
down_revision: Union[str, None] = "e5a8b1c4f9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CASCADES = [
    ("sources", "sources_user_id_fkey", "user_id"),
    ("article_feedbacks", "article_feedbacks_user_id_fkey", "user_id"),
    ("article_impressions", "article_impressions_user_id_fkey", "user_id"),
    (
        "article_relevance_scores",
        "article_relevance_scores_user_id_fkey",
        "user_id",
    ),
    ("keyword_weights", "keyword_weights_user_id_fkey", "user_id"),
]


def upgrade() -> None:
    for table, fk_name, local_col in _CASCADES:
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.create_foreign_key(
            fk_name,
            table,
            "users",
            [local_col],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table, fk_name, local_col in _CASCADES:
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.create_foreign_key(
            fk_name,
            table,
            "users",
            [local_col],
            ["id"],
        )
