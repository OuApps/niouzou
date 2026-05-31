"""Explore History tests (E9-S3).

- Returns articles the user has impressed, newest seen first.
- Keyset paginates stably on (seen_at, id).
- Carries the per-user feedback state (reaction / is_saved / read).
"""

from datetime import datetime, timedelta, timezone

from niouzou.models import ArticleImpression
from niouzou.services.explore_service import ExploreService
from niouzou.services.feedback_service import FeedbackService
from tests.factories import (
    feedback_request,
    make_article,
    make_source,
    make_user,
    set_relevance,
)

NOW = datetime.now(timezone.utc)


async def _seen(session, article, user, *, when):
    session.add(
        ArticleImpression(article_id=article.id, user_id=user.id, seen_at=when)
    )


async def test_history_returns_impressed_articles_newest_first(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    older = await make_article(db_session, source, title="older")
    newer = await make_article(db_session, source, title="newer")
    await set_relevance(db_session, older, user, 0.4)
    await set_relevance(db_session, newer, user, 0.4)
    await _seen(db_session, older, user, when=NOW - timedelta(hours=2))
    await _seen(db_session, newer, user, when=NOW - timedelta(minutes=10))
    await db_session.commit()

    res = await ExploreService(db_session).list_history(
        user.id, cursor=None, limit=None
    )
    assert [a.title for a in res.articles] == ["newer", "older"]
    assert res.has_more is False


async def test_history_excludes_unseen_articles(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    seen = await make_article(db_session, source, title="seen")
    unseen = await make_article(db_session, source, title="unseen")
    await set_relevance(db_session, seen, user, 0.5)
    await set_relevance(db_session, unseen, user, 0.5)
    await _seen(db_session, seen, user, when=NOW)
    await db_session.commit()

    res = await ExploreService(db_session).list_history(
        user.id, cursor=None, limit=None
    )
    assert [a.title for a in res.articles] == ["seen"]


async def test_history_excludes_other_users_impressions(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    my_src = await make_source(db_session, me, feed_id=1)
    other_src = await make_source(db_session, other, feed_id=2)
    mine = await make_article(db_session, my_src, title="mine")
    theirs = await make_article(db_session, other_src, title="theirs")
    await _seen(db_session, mine, me, when=NOW - timedelta(minutes=5))
    await _seen(db_session, theirs, other, when=NOW)
    await db_session.commit()

    res = await ExploreService(db_session).list_history(me.id, cursor=None, limit=None)
    assert [a.title for a in res.articles] == ["mine"]


async def test_history_pagination_no_overlap(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(5):
        art = await make_article(db_session, source, title=f"a{i}")
        await set_relevance(db_session, art, user, 0.4)
        await _seen(db_session, art, user, when=NOW - timedelta(minutes=i))
    await db_session.commit()

    svc = ExploreService(db_session)
    page1 = await svc.list_history(user.id, cursor=None, limit=2)
    assert page1.has_more is True
    page2 = await svc.list_history(user.id, cursor=page1.next_cursor, limit=2)
    page3 = await svc.list_history(user.id, cursor=page2.next_cursor, limit=2)

    ids = [a.id for p in (page1, page2, page3) for a in p.articles]
    assert len(ids) == len(set(ids)) == 5
    assert page3.has_more is False


async def test_history_carries_feedback_state(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, title="x")
    await set_relevance(db_session, article, user, 0.5)
    await _seen(db_session, article, user, when=NOW)
    await db_session.commit()

    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, reaction="like", is_saved=True)
    )
    await db_session.commit()

    res = await ExploreService(db_session).list_history(
        user.id, cursor=None, limit=None
    )
    assert len(res.articles) == 1
    item = res.articles[0]
    assert item.reaction == "like"
    assert item.is_saved is True
    assert item.read_full_article is False
    assert item.seen_at is not None
