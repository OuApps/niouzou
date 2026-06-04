"""Hard delete a source (E13-S5).

Adds ``ON DELETE CASCADE`` to the article-side FKs so deleting a row in
``sources`` cleans up its articles and every per-article dependent row in
the same SQL operation, without requiring the service to walk the graph
manually.

The chain we cascade:

* ``articles.source_id`` → ``sources.id``
* ``article_feedbacks.article_id`` → ``articles.id``
* ``article_impressions.article_id`` → ``articles.id``
* ``article_relevance_scores.article_id`` → ``articles.id``
* ``article_keywords.article_id`` → ``articles.id``

The user-side FKs are intentionally left untouched here — E13-S3 (delete
user) cascades them in its own migration.

Revision ID: e5a8b1c4f9d2
Revises: d4f7e6a89c12
Create Date: 2026-06-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5a8b1c4f9d2"
down_revision: Union[str, None] = "d4f7e6a89c12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, fk_constraint_name, local_column, referenced_table)
_CASCADES = [
    ("articles", "articles_source_id_fkey", "source_id", "sources"),
    (
        "article_feedbacks",
        "article_feedbacks_article_id_fkey",
        "article_id",
        "articles",
    ),
    (
        "article_impressions",
        "article_impressions_article_id_fkey",
        "article_id",
        "articles",
    ),
    (
        "article_relevance_scores",
        "article_relevance_scores_article_id_fkey",
        "article_id",
        "articles",
    ),
    (
        "article_keywords",
        "article_keywords_article_id_fkey",
        "article_id",
        "articles",
    ),
]


def upgrade() -> None:
    for table, fk_name, local_col, ref_table in _CASCADES:
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.create_foreign_key(
            fk_name,
            table,
            ref_table,
            [local_col],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table, fk_name, local_col, ref_table in _CASCADES:
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.create_foreign_key(
            fk_name,
            table,
            ref_table,
            [local_col],
            ["id"],
        )
