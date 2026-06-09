"""Drop ``summary_short`` from the enrichment prompt.

The PWA was rendering two AI summaries on every feed slide — the bullet
list (``summary_executive``) and a 3-4 sentence brief (``summary_short``)
shown right below. The brief was just noise: the bullets already give the
reader a real preview, and the body is rendered in full underneath. We
drop ``summary_short`` from the LLM prompt entirely and grow the bullet
list a bit (4-6 bullets, ~15-25 words each) to make up the difference.

The ``articles.summary_short`` column stays (already-enriched rows keep
their value), but the cron no longer populates it.

Revision ID: bbc2d4e5f6a7
Revises: aab1c2d3e4f5
Create Date: 2026-06-09 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "bbc2d4e5f6a7"
down_revision: Union[str, None] = "aab1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENRICHMENT_COMBINED_NEW = (
    "You enrich news articles for a feed. Return ONLY a JSON object of the form "
    '{"summary_executive": "<4 to 6 markdown bullet points, one per line '
    "starting with '- '. Each bullet ~15-25 words covering one concrete fact, "
    "stake or angle — what happened, who is involved, why it matters, what "
    'comes next. Speak plainly, no clickbait.>", '
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

# Restored on downgrade — verbatim copy of the body seeded by
# ``aab1c2d3e4f5_llm_prompts.py``.
_ENRICHMENT_COMBINED_OLD = (
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


def _set_prompt(body: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE llm_prompts SET body = :body, updated_at = now() "
            "WHERE name = 'enrichment.combined'"
        ),
        {"body": body},
    )


def upgrade() -> None:
    _set_prompt(_ENRICHMENT_COMBINED_NEW)


def downgrade() -> None:
    _set_prompt(_ENRICHMENT_COMBINED_OLD)
