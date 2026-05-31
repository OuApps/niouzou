"""Partial-upsert semantics of POST /feedback (E9-S1).

A field set to ``None`` (or omitted) must not touch the existing column value.
``read_full_article`` is monotone — ``False`` is silently dropped, never
overwriting a previous ``True``. A payload with all three fields ``None`` is
rejected by the router with 400 (covered by the API-level test in
``test_endpoints`` integration tests at a later stage; here we test the
``is_no_op`` helper directly).
"""

from sqlalchemy import select

from niouzou.models import ArticleFeedback
from niouzou.schemas.feedback import FeedbackRequest
from niouzou.services.feedback_service import FeedbackService
from tests.factories import (
    feedback_request,
    make_article,
    make_source,
    make_user,
)


async def _row(session, user, article) -> ArticleFeedback:
    return await session.scalar(
        select(ArticleFeedback).where(
            ArticleFeedback.user_id == user.id,
            ArticleFeedback.article_id == article.id,
        )
    )


async def test_is_saved_alone_does_not_touch_reaction(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await db_session.commit()

    svc = FeedbackService(db_session)

    # Seed with a like.
    await svc.record(user.id, feedback_request(article.id, reaction="like"))
    await db_session.commit()

    # Now flip is_saved on — reaction must stay 'like'.
    await svc.record(user.id, feedback_request(article.id, is_saved=True))
    await db_session.commit()

    row = await _row(db_session, user, article)
    assert row.reaction == "like"
    assert row.is_saved is True
    assert row.read_full_article is False


async def test_reaction_none_clears_without_touching_is_saved(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(
        user.id,
        FeedbackRequest(article_id=article.id, reaction="like", is_saved=True),
    )
    await db_session.commit()

    # reaction='none' explicit clears the like; is_saved must stay True.
    await svc.record(user.id, feedback_request(article.id, reaction="none"))
    await db_session.commit()

    row = await _row(db_session, user, article)
    assert row.reaction == "none"
    assert row.is_saved is True


async def test_read_full_article_false_is_silently_ignored(db_session):
    """E9-S1: read_full_article is monotone — false never overwrites true."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await db_session.commit()

    svc = FeedbackService(db_session)

    # First call: mark as read.
    response = await svc.record(
        user.id, feedback_request(article.id, read_full_article=True)
    )
    await db_session.commit()
    assert response.read_full_article is True

    # Sending false explicitly must NOT downgrade.
    response = await svc.record(
        user.id, feedback_request(article.id, read_full_article=False)
    )
    await db_session.commit()
    assert response.read_full_article is True

    row = await _row(db_session, user, article)
    assert row.read_full_article is True


async def test_read_full_article_false_on_first_call_inserts_false(db_session):
    """The silent-drop rule should not prevent the initial insert from happening
    when other fields are set — the column simply gets its default (false)."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await db_session.commit()

    await FeedbackService(db_session).record(
        user.id,
        FeedbackRequest(
            article_id=article.id, reaction="like", read_full_article=False
        ),
    )
    await db_session.commit()

    row = await _row(db_session, user, article)
    assert row.reaction == "like"
    assert row.read_full_article is False


async def test_empty_payload_is_detected(db_session):
    """The router (not the schema) returns 400; here we just confirm the
    detection helper sees the no-op."""
    req = FeedbackRequest(article_id="00000000-0000-0000-0000-000000000000")
    assert req.is_no_op() is True

    assert (
        FeedbackRequest(
            article_id="00000000-0000-0000-0000-000000000000",
            is_saved=False,
        ).is_no_op()
        is False
    )
