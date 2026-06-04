"""LLM prompts moved to DB (E13-S2).

Creates ``llm_prompts(name PK, body, updated_at)`` and seeds the three
prompts that were previously hardcoded:

  * ``enrichment.combined`` — combined summary + keywords prompt used by
    ``EnrichmentService``. The summary_short instruction is rewritten as
    a longer 3-4 sentence brief (vs the previous 2 sentences) — the
    short form was too thin to give the reader a real preview of the
    article before the click.
  * ``compaction.system`` — keyword compaction prompt used by
    ``CompactionService``.
  * ``scoring.ai_keywords`` — keyword-only prompt used by the standalone
    ``AIKeywordScorer`` (kept as a separate row even though
    ``EnrichmentService`` is the primary path — the scorer is still
    referenced by the pipeline factory).

Once this migration runs, the constants in the Python modules become
fallback defaults only used at module-import time before the per-run
loader replaces them; on the next pipeline run the DB value wins.

Revision ID: aab1c2d3e4f5
Revises: f6b9c2d18e4a
Create Date: 2026-06-04 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aab1c2d3e4f5"
down_revision: Union[str, None] = "f6b9c2d18e4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENRICHMENT_COMBINED = (
    "You enrich news articles for a feed. Return ONLY a JSON object of the form "
    '{"summary_short": "<3 to 4 engaging sentences (around 60-100 words) that '
    "give the reader a real preview of the article: what happened, why it "
    "matters, and one concrete detail or stake. Avoid clickbait phrasing — "
    'speak plainly, do not tease.>", '
    '"summary_executive": "<3-5 markdown bullet points, one per line starting with \'- \'>", '
    '"keywords": [{"term": "<lowercase 1-3 word topic>", "salience": <0.0-1.0>}]}. '
    "At most 10 keywords. Aim for: 3-4 broad categories (e.g., Science, Sports, Politics, "
    "Technology) and 3-4 specific/entity keywords (e.g., person names, company names, places). "
    "salience = how central the topic is (1.0 = main subject). "
    "Keywords should be stable reusable concepts — prefer named entities (clubs, "
    "countries, people, companies), domains (football, AI, finance) and topics "
    "(climate, elections) over ephemeral events or actions ('defeat', 'final', "
    "'Argentine midfielder'). Normalise names consistently. "
    "Respond in the language specified in the 'Language:' field, or in the "
    "article's language if unspecified. No preamble, no commentary."
)

_COMPACTION_SYSTEM = (
    "You are a knowledge-base curator. Given a list of keyword terms used to "
    "tag news articles, group the terms that refer to the same concept. "
    "Return ONLY a JSON object of the form "
    '{"groups": [{"canonical": "<preferred form>", "aliases": ["<other 1>", "<other 2>"]}]}. '
    "Rules: canonical is the cleanest, most widely recognised form. aliases "
    "must NOT contain canonical. Only include groups with at least 2 members. "
    "Be conservative — when in doubt, do not merge. Skip groups whose members "
    "are merely topically related (e.g. 'climate' and 'pollution'). "
    "All terms are lowercased; preserve case. No preamble."
)

_AI_KEYWORDS_SYSTEM = (
    "You extract the key topics from a news article. "
    "Return ONLY a JSON object of the form "
    '{"keywords": [{"term": "<lowercase topic>", "salience": <0.0-1.0>}]}. '
    "salience = how central the topic is to the article (1.0 = the main "
    "subject). Use short noun phrases (1-3 words), at most 15 keywords, "
    "no duplicates, no commentary."
)


_SEED = [
    ("enrichment.combined", _ENRICHMENT_COMBINED),
    ("compaction.system", _COMPACTION_SYSTEM),
    ("scoring.ai_keywords", _AI_KEYWORDS_SYSTEM),
]


def upgrade() -> None:
    op.create_table(
        "llm_prompts",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    prompts = sa.table(
        "llm_prompts",
        sa.column("name", sa.Text()),
        sa.column("body", sa.Text()),
    )
    op.bulk_insert(
        prompts, [{"name": name, "body": body} for name, body in _SEED]
    )


def downgrade() -> None:
    op.drop_table("llm_prompts")
