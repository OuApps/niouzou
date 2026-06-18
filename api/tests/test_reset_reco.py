"""Reco-reset tests (E17-S5).

``FeedbackService.reset_reco`` wipes the learned recommendation signal —
like/dislike reactions and learned ``keyword_weights`` — while preserving the
Saved library, read flags and pinned keywords. DB-backed; skipped when Postgres
is unreachable (see conftest).
"""

from sqlalchemy import select

from niouzou.models import ArticleFeedback, KeywordWeight
from niouzou.services.feedback_service import FeedbackService
from tests.factories import (
    add_keyword,
    feedback_request,
    make_article,
    make_source,
    make_user,
)


async def _feedback(session, user):
    return await session.scalar(
        select(ArticleFeedback).where(ArticleFeedback.user_id == user.id)
    )


async def _weight(session, user, term):
    return await session.scalar(
        select(KeywordWeight).where(
            KeywordWeight.user_id == user.id, KeywordWeight.term == term
        )
    )


async def test_reset_clears_pure_reaction_and_learned_weight(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.8)
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(user.id, feedback_request(article.id, reaction="like"))
    await db_session.commit()

    result = await svc.reset_reco(user.id)
    await db_session.commit()

    assert result.reactions_cleared == 1
    assert result.weights_deleted == 1
    # Pure-reaction row deleted outright; learned weight gone.
    assert await _feedback(db_session, user) is None
    assert await _weight(db_session, user, "rust") is None


async def test_reset_keeps_saved_row_but_neutralises_reaction(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.8)
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(
        user.id, feedback_request(article.id, reaction="like", is_saved=True)
    )
    await db_session.commit()

    await svc.reset_reco(user.id)
    await db_session.commit()

    fb = await _feedback(db_session, user)
    assert fb is not None  # Saved library preserved
    assert fb.is_saved is True
    assert fb.reaction == "none"  # like cleared
    assert await _weight(db_session, user, "rust") is None


async def test_reset_preserves_pinned_weight(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.8)
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(user.id, feedback_request(article.id, reaction="like"))
    await db_session.commit()

    db_session.add(
        KeywordWeight(
            user_id=user.id, term="python", weight=5.0, manually_overridden=True
        )
    )
    await db_session.commit()

    await svc.reset_reco(user.id)
    await db_session.commit()

    pinned = await _weight(db_session, user, "python")
    assert pinned is not None and pinned.weight == 5.0  # pin kept
    assert await _weight(db_session, user, "rust") is None  # learned dropped


async def test_reset_is_idempotent_and_safe_on_empty(db_session):
    user = await make_user(db_session)
    await db_session.commit()

    result = await FeedbackService(db_session).reset_reco(user.id)
    await db_session.commit()

    assert result.reactions_cleared == 0
    assert result.weights_deleted == 0
