"""GET /feed?start=:id pivot tests (E9-S3).

- Pivot article comes first.
- Already-impressed pivot is accepted (impression filter is overridden for
  that one article).
- The rest of the page continues from the pivot's feed_rank.
- A foreign / pending pivot returns 404.
"""

from datetime import datetime, timedelta, timezone

import pytest

from niouzou.errors import APIError
from niouzou.models import ArticleImpression
from niouzou.models.article import STATUS_PENDING
from niouzou.services.feed_service import FeedService
from tests.factories import make_article, make_source, make_user, set_relevance

NOW = datetime.now(timezone.utc)


async def test_start_article_is_first(db_session):
    """The pivot lands at slot 0 and the rest of the page continues from its
    feed_rank — i.e. only articles ranked BELOW the pivot follow it. Build a
    fixture where the pivot is ranked highest so we see the tail behind it."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    pivot = await make_article(db_session, source, title="pivot", published_at=NOW)
    lower = await make_article(
        db_session, source, title="lower", published_at=NOW - timedelta(hours=12)
    )
    await set_relevance(db_session, pivot, user, 0.7)
    await set_relevance(db_session, lower, user, 0.3)
    await db_session.commit()

    feed = await FeedService(db_session).get_feed(
        user.id, cursor=None, limit=None, start=pivot.id
    )
    titles = [a.title for a in feed.articles]
    assert titles[0] == "pivot"
    assert "lower" in titles[1:]


async def test_start_overrides_impression_filter(db_session):
    """Already-impressed pivots are re-surfaced — that's the Explore History flow."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    pivot = await make_article(db_session, source, title="impressed")
    fresh = await make_article(db_session, source, title="fresh")
    await set_relevance(db_session, pivot, user, 0.5)
    await set_relevance(db_session, fresh, user, 0.5)
    db_session.add(ArticleImpression(article_id=pivot.id, user_id=user.id))
    await db_session.commit()

    feed = await FeedService(db_session).get_feed(
        user.id, cursor=None, limit=None, start=pivot.id
    )
    titles = [a.title for a in feed.articles]
    assert titles[0] == "impressed"
    # The regular branch still filters impressions out — pivot must not be
    # duplicated even though it appears at the top.
    assert titles.count("impressed") == 1


async def test_start_ignored_when_cursor_provided(db_session):
    """Subsequent pages of a paginated feed are not affected by start."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(3):
        art = await make_article(
            db_session, source, title=f"a{i}", published_at=NOW - timedelta(hours=i)
        )
        await set_relevance(db_session, art, user, 0.5)
    pivot = await make_article(db_session, source, title="pivot", published_at=NOW)
    await set_relevance(db_session, pivot, user, 0.5)
    await db_session.commit()

    svc = FeedService(db_session)
    page1 = await svc.get_feed(user.id, cursor=None, limit=2)
    # Pivot ignored — fetching with cursor + start, pivot must NOT be re-injected.
    page2 = await svc.get_feed(
        user.id, cursor=page1.next_cursor, limit=2, start=pivot.id
    )
    page1_titles = [a.title for a in page1.articles]
    page2_titles = [a.title for a in page2.articles]
    assert set(page1_titles) & set(page2_titles) == set()


async def test_start_404_when_article_belongs_to_other_user(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    other_src = await make_source(db_session, other, feed_id=2)
    foreign = await make_article(db_session, other_src, title="foreign")
    await set_relevance(db_session, foreign, other, 0.5)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await FeedService(db_session).get_feed(
            me.id, cursor=None, limit=None, start=foreign.id
        )
    assert exc.value.status_code == 404


async def test_start_404_when_article_is_pending(db_session):
    from niouzou.models import Article

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    pending = Article(
        source_id=source.id,
        miniflux_entry_id=777_001,
        url="https://example.com/x",
        title="pending",
        status=STATUS_PENDING,
    )
    db_session.add(pending)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None, start=pending.id
        )
    assert exc.value.status_code == 404
