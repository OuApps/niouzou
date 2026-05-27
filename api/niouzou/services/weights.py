"""Keyword-weight recomputation, shared by the feedback path and the cron.

The weight of a (user, term) pair is, per docs/DATA_MODEL.md:

    weight = Σ salience(term, article) × feedback_value(action)
    feedback_value: like|save = +1, dislike = -1, skip = 0

Both entry points recompute from scratch over ``article_feedbacks`` (the source
of truth), so the operation is idempotent. Rows flagged ``manually_overridden``
are never touched.
"""

import uuid

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# Maps an action to its weight contribution. `save` counts as a like.
_FEEDBACK_VALUE = (
    "CASE fb.action "
    "WHEN 'like' THEN 1 WHEN 'save' THEN 1 WHEN 'dislike' THEN -1 ELSE 0 END"
)

# Aggregate (user, term) → weight + counts from feedbacks joined to keywords.
_AGGREGATE = f"""
SELECT
    fb.user_id AS user_id,
    ak.term AS term,
    COALESCE(SUM(ak.salience * {_FEEDBACK_VALUE}), 0) AS weight,
    COUNT(*) FILTER (WHERE fb.action IN ('like', 'save')) AS like_count,
    COUNT(*) FILTER (WHERE fb.action = 'dislike') AS dislike_count
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
    preserved. ``article_relevance_scores`` is never touched.
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
