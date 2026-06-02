"""Keyword-weight recomputation, shared by the feedback path and the cron.

Per E9-S1, an article's contribution to its keywords' weights is:

    salience(term, article) × (
        +1.0 if reaction = 'like'  else
        -1.0 if reaction = 'dislike' else 0
      + 0.5 if is_saved
      + 0.5 if read_full_article
    )

Signals accumulate across articles. Like+save+read = +2.0 × salience.
Dislike+save = -0.5 × salience (rare but legal — user wants the article for
reference but disagrees with its premise). All-neutral rows (which used to
exist as `action='skip'` and were dropped at migration time) contribute 0.

Both entry points recompute from scratch over ``article_feedbacks`` (the
source of truth), so the operation is idempotent. Rows flagged
``manually_overridden`` are never touched.
"""

import uuid

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# Per-feedback signal contribution. Mirrors the formula in docs/EPICS.md (E9-S1).
_FEEDBACK_VALUE = (
    "("
    "CASE fb.reaction WHEN 'like' THEN 1.0 "
    "WHEN 'dislike' THEN -1.0 ELSE 0 END "
    "+ CASE WHEN fb.is_saved          THEN 0.5 ELSE 0 END "
    "+ CASE WHEN fb.read_full_article THEN 0.5 ELSE 0 END"
    ")"
)

# Per E9-S1, like_count / dislike_count are repurposed for the Keywords UI:
#   like_count    = rows with a positive contribution (liked OR saved)
#   dislike_count = rows with a disliked reaction (saved/read don't downweight)
_AGGREGATE = f"""
SELECT
    fb.user_id AS user_id,
    ak.term AS term,
    COALESCE(SUM(ak.salience * {_FEEDBACK_VALUE}), 0) AS weight,
    COUNT(*) FILTER (
        WHERE fb.reaction = 'like' OR fb.is_saved
    ) AS like_count,
    COUNT(*) FILTER (WHERE fb.reaction = 'dislike') AS dislike_count
FROM article_keywords ak
JOIN article_feedbacks fb ON fb.article_id = ak.article_id
"""

# Upsert that skips manually overridden rows (their weight is user-pinned).
_UPSERT_TAIL = """
ON CONFLICT (user_id, term) DO UPDATE
SET weight = EXCLUDED.weight,
    like_count = EXCLUDED.like_count,
    dislike_count = EXCLUDED.dislike_count,
    updated_at = now()
WHERE keyword_weights.manually_overridden = false
"""


async def recompute_for_terms(
    session: AsyncSession, user_id: uuid.UUID, terms: list[str]
) -> None:
    """Synchronously recompute weights for ``terms`` of a single user.

    Used on the feedback path. Locks the affected rows in a stable order so
    concurrent feedback calls touching the same term serialise instead of
    racing to a lost update (E3-S6 acceptance criterion).
    """
    if not terms:
        return

    # 1. Materialise the rows so there is something to lock, even for terms the
    #    user has never seen before.
    ensure = text(
        """
        INSERT INTO keyword_weights (user_id, term)
        SELECT :user_id, t FROM unnest(CAST(:terms AS text[])) AS t
        ON CONFLICT (user_id, term) DO NOTHING
        """
    )
    await session.execute(ensure, {"user_id": user_id, "terms": terms})

    # 2. Lock them in term order (deadlock-free), forcing competitors to wait
    #    here until our transaction commits.
    lock = text(
        "SELECT 1 FROM keyword_weights "
        "WHERE user_id = :user_id AND term IN :terms ORDER BY term FOR UPDATE"
    ).bindparams(bindparam("terms", expanding=True))
    await session.execute(lock, {"user_id": user_id, "terms": terms})

    # 3. Recompute. Now that the lock is held, the aggregate sees every feedback
    #    committed by transactions that ran before us.
    recompute = text(
        f"""
        INSERT INTO keyword_weights
            (user_id, term, weight, like_count, dislike_count)
        {_AGGREGATE}
        WHERE fb.user_id = :user_id AND ak.term IN :terms
        GROUP BY fb.user_id, ak.term
        {_UPSERT_TAIL}
        """
    ).bindparams(bindparam("terms", expanding=True))
    await session.execute(recompute, {"user_id": user_id, "terms": terms})


async def recompute_all(session: AsyncSession) -> None:
    """Full recompute of every user's weights — the daily cron's safety net.

    Idempotent: running twice yields identical rows. Overridden rows are
    preserved. ``article_relevance_scores.relevance_score`` is never
    recomputed here — scores are frozen at enrichment. The cron does flip
    ``is_cold_start`` back to FALSE for rows whose keywords have since
    gained a user weight (see ``demote_cold_flags``).
    """
    statement = text(
        f"""
        INSERT INTO keyword_weights
            (user_id, term, weight, like_count, dislike_count)
        {_AGGREGATE}
        GROUP BY fb.user_id, ak.term
        {_UPSERT_TAIL}
        """
    )
    await session.execute(statement)


async def demote_cold_flags(session: AsyncSession) -> int:
    """Flip ``is_cold_start`` to FALSE on rows whose keywords are no longer
    unknown to the user (E10-S4).

    Called after ``recompute_all`` in the daily cron. A row was stamped cold
    at enrichment if NONE of its article's keywords matched a user's
    ``keyword_weights``. Once the user feedbacks something that creates a
    weight on a shared term, every cold row for that term is stale.

    The query only touches rows currently flagged cold, so the scan is cheap
    even as the table grows. Returns the number of rows updated for
    telemetry.

    Symmetric warm→cold transitions are intentionally not handled here:
    losing every keyword weight is rare (compaction never deletes pinned
    rows; manual resets are explicit user actions) and the article will be
    re-stamped if it ever passes back through the scorer.
    """
    result = await session.execute(
        text(
            """
            UPDATE article_relevance_scores AS ars
            SET is_cold_start = FALSE
            WHERE ars.is_cold_start = TRUE
              AND EXISTS (
                SELECT 1
                FROM article_keywords ak
                JOIN keyword_weights kw
                  ON kw.term = ak.term AND kw.user_id = ars.user_id
                WHERE ak.article_id = ars.article_id
              )
            """
        )
    )
    return result.rowcount or 0
