"""Keyword-weight recompute tests (E3-S6 synchronous + E3-S8 cron).

DB-backed; skipped automatically when Postgres is unreachable (see conftest).
"""

from sqlalchemy import select

from niouzou.models import KeywordWeight
from niouzou.services.feedback_service import FeedbackService
from niouzou.services.weights import recompute_all
from tests.factories import add_keyword, make_article, make_source, make_user


async def _weight(session, user, term) -> KeywordWeight | None:
    return await session.scalar(
        select(KeywordWeight).where(
            KeywordWeight.user_id == user.id, KeywordWeight.term == term
        )
    )


async def test_like_creates_positive_weight(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.8)
    await db_session.commit()

    await FeedbackService(db_session).record(user.id, article.id, "like")
    await db_session.commit()

    kw = await _weight(db_session, user, "rust")
    assert kw.weight == 0.8  # salience 0.8 × (+1)
    assert kw.like_count == 1
    assert kw.dislike_count == 0


async def test_changing_like_to_dislike_flips_weight(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.5)
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(user.id, article.id, "like")
    await db_session.commit()
    await svc.record(user.id, article.id, "dislike")
    await db_session.commit()

    kw = await _weight(db_session, user, "rust")
    assert kw.weight == -0.5
    assert kw.like_count == 0
    assert kw.dislike_count == 1


async def test_save_counts_as_like(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.6)
    await db_session.commit()

    await FeedbackService(db_session).record(user.id, article.id, "save")
    await db_session.commit()

    kw = await _weight(db_session, user, "rust")
    assert kw.weight == 0.6
    assert kw.like_count == 1


async def test_repeated_like_is_idempotent(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.7)
    await db_session.commit()

    svc = FeedbackService(db_session)
    for _ in range(4):  # like × 4 == like × 1
        await svc.record(user.id, article.id, "like")
        await db_session.commit()

    kw = await _weight(db_session, user, "rust")
    assert kw.weight == 0.7
    assert kw.like_count == 1


async def test_weight_sums_across_articles(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    a1 = await make_article(db_session, source)
    a2 = await make_article(db_session, source)
    await add_keyword(db_session, a1, "rust", 0.5)
    await add_keyword(db_session, a2, "rust", 0.3)
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(user.id, a1.id, "like")
    await db_session.commit()
    await svc.record(user.id, a2.id, "dislike")
    await db_session.commit()

    kw = await _weight(db_session, user, "rust")
    assert abs(kw.weight - 0.2) < 1e-9  # 0.5×(+1) + 0.3×(-1)
    assert kw.like_count == 1 and kw.dislike_count == 1


async def test_cron_recompute_is_idempotent_and_matches_sync(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.4)
    await db_session.commit()

    await FeedbackService(db_session).record(user.id, article.id, "like")
    await db_session.commit()

    await recompute_all(db_session)
    await db_session.commit()
    first = (await _weight(db_session, user, "rust")).weight

    await recompute_all(db_session)
    await db_session.commit()
    second = (await _weight(db_session, user, "rust")).weight

    assert first == second == 0.4


async def test_cron_preserves_manually_overridden(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.9)
    await db_session.commit()

    await FeedbackService(db_session).record(user.id, article.id, "like")
    await db_session.commit()

    # Manually pin the weight.
    kw = await _weight(db_session, user, "rust")
    kw.weight = 5.0
    kw.manually_overridden = True
    await db_session.commit()

    await recompute_all(db_session)
    await db_session.commit()

    assert (await _weight(db_session, user, "rust")).weight == 5.0


async def test_sync_recompute_skips_overridden(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.9)
    await db_session.commit()

    # Pin before any feedback.
    db_session.add(
        KeywordWeight(
            user_id=user.id, term="rust", weight=3.0, manually_overridden=True
        )
    )
    await db_session.commit()

    await FeedbackService(db_session).record(user.id, article.id, "like")
    await db_session.commit()

    assert (await _weight(db_session, user, "rust")).weight == 3.0
