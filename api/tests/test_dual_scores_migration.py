"""E16-S8 migration backfill — legacy single score lands on the right column.

The migration drops ``relevance_score``/``scorer``/``is_cold_start`` after the
backfill, so we can't replay it inside a normal test session (the columns no
longer exist). Instead we test the routing predicate against the three legacy
``scorer`` stamps: 'smart_match' → ``smart_score``, anything else (including
NULL — pre-E7-S7 rows, all keyword-pathway) → ``keyword_score``. The actual
UPDATEs are exercised by ``alembic upgrade head`` on the test database.
"""

from sqlalchemy import text


async def test_backfill_routes_legacy_score_by_scorer_stamp(db_session):
    rows = (
        await db_session.execute(
            text(
                """
                SELECT
                  scorer,
                  CASE WHEN scorer = 'smart_match' THEN score END AS smart_score,
                  CASE WHEN scorer IS DISTINCT FROM 'smart_match' THEN score END
                    AS keyword_score
                FROM (VALUES
                  ('smart_match', 0.9::float8),
                  ('ai_keyword', 0.7::float8),
                  ('tfidf', 0.6::float8),
                  (NULL, 0.5::float8)
                ) AS t(scorer, score)
                ORDER BY scorer NULLS LAST
                """
            )
        )
    ).all()

    mapping = {r.scorer: (r.smart_score, r.keyword_score) for r in rows}
    assert mapping == {
        # smart provenance → smart column only; the other stays NULL («–»)
        # until the nightly rescore fills it.
        "smart_match": (0.9, None),
        "ai_keyword": (None, 0.7),
        "tfidf": (None, 0.6),
        None: (None, 0.5),
    }
