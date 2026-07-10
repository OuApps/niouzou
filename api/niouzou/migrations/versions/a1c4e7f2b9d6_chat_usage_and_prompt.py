"""Chat cost attribution + editable chat system prompt (E21-S8).

Two additions for the article chat:

* ``llm_usage_log.usage`` — tags each row with what spent the money
  (``'enrichment'`` | ``'chat'``) so ``/stats`` can break the OpenRouter
  bill down per usage. Existing rows were all written by the enrichment
  path, hence the server default.

* seeds the ``chat.system`` row in ``llm_prompts`` — the admin-editable
  *instruction* part of the chat system prompt. The article context
  (title + summary + content) is always appended by ``ChatService``,
  never editable, so an admin edit can't break the grounding.

Revision ID: a1c4e7f2b9d6
Revises: f4b8d2a91c63
Create Date: 2026-07-10
"""

import sqlalchemy as sa
from alembic import op

revision = "a1c4e7f2b9d6"
down_revision = "f4b8d2a91c63"
branch_labels = None
depends_on = None


# Keep in sync with the fallback constant in ``services/chat_service.py``
# (used when this row is missing, e.g. mid-migration).
_CHAT_SYSTEM = (
    "You are Niouzou's reading assistant. The user is reading the news "
    "article below and wants to discuss it: ask for clarifications, dig "
    "into a point, or broaden the topic. Ground your answers in the "
    "article; when the user goes beyond it, you may use general knowledge "
    "but say you are doing so. Be concise. Answer in the language the user "
    "writes in."
)


def upgrade() -> None:
    op.add_column(
        "llm_usage_log",
        sa.Column(
            "usage",
            sa.String(),
            nullable=False,
            server_default="enrichment",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO llm_prompts (name, body) VALUES (:name, :body) "
            "ON CONFLICT (name) DO NOTHING"
        ).bindparams(name="chat.system", body=_CHAT_SYSTEM)
    )


def downgrade() -> None:
    op.execute("DELETE FROM llm_prompts WHERE name = 'chat.system'")
    op.drop_column("llm_usage_log", "usage")
