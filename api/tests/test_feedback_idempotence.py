"""E9-S1 cron idempotence — recompute_all twice must produce identical rows.

The expected outcome is the same KeywordWeight rows after two successive
`recompute_all` runs against a stable feedback set, down to the weight value
itself (no float drift).
"""

from sqlalchemy import select

from niouzou.models import KeywordWeight
from niouzou.services.feedback_service import FeedbackService
from niouzou.services.weights import recompute_all
from tests.factories import (
    add_keyword,
    feedback_request,
    make_article,
    make_source,
    make_user,
)


async def _snapshot(session, user_id):
    rows = (
        await session.execute(
            select(
                KeywordWeight.term,
                KeywordWeight.weight,
                KeywordWeight.like_count,
                KeywordWeight.dislike_count,
            ).where(KeywordWeight.user_id == user_id)
            .order_by(KeywordWeight.term)
        )
    ).all()
    return [(r.term, r.weight, r.like_count, r.dislike_count) for r in rows]


async def test_recompute_all_is_idempotent_across_mixed_feedback(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)

    a1 = await make_article(db_session, source, title="ai")
    a2 = await make_article(db_session, source, title="ml")
    a3 = await make_article(db_session, source, title="rust")
    await add_keyword(db_session, a1, "ai", 0.9)
    await add_keyword(db_session, a1, "ml", 0.5)
    await add_keyword(db_session, a2, "ml", 0.8)
    await add_keyword(db_session, a3, "rust", 0.7)
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(user.id, feedback_request(a1.id, reaction="like", is_saved=True))
    await db_session.commit()
    await svc.record(user.id, feedback_request(a2.id, reaction="dislike"))
    await db_session.commit()
    await svc.record(
        user.id, feedback_request(a3.id, reaction="like", read_full_article=True)
    )
    await db_session.commit()

    await recompute_all(db_session)
    await db_session.commit()
    snapshot_a = await _snapshot(db_session, user.id)

    await recompute_all(db_session)
    await db_session.commit()
    snapshot_b = await _snapshot(db_session, user.id)

    assert snapshot_a == snapshot_b
    # Sanity-check: the snapshot covers all three terms.
    terms = {row[0] for row in snapshot_a}
    assert terms == {"ai", "ml", "rust"}
