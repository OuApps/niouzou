"""Explore New tests (E9-S3).

- Returns enriched articles the user has NOT impressed, gravity-ranked.
- SCORE_THRESHOLD must NOT gate this view (the user is explicitly scanning).
- RANDOM_SURFACE_RATE must NOT add noise — ordering is deterministic.
"""

from datetime import datetime, timedelta, timezone

from niouzou.config import get_settings
from niouzou.models import ArticleImpression
from niouzou.services.explore_service import ExploreService
from tests.factories import make_article, make_source, make_user, set_relevance

NOW = datetime.now(timezone.utc)


async def test_new_excludes_impressed_articles(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    seen = await make_article(db_session, source, title="seen")
    unseen = await make_article(db_session, source, title="unseen")
    await set_relevance(db_session, seen, user, 0.6)
    await set_relevance(db_session, unseen, user, 0.6)
    db_session.add(ArticleImpression(article_id=seen.id, user_id=user.id))
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None
    )
    assert [a.title for a in res.articles] == ["unseen"]


async def test_new_orders_by_gravity_not_pure_relevance(db_session):
    """Higher feed_rank wins: an older high-relevance article can still come
    second behind a fresher mid-relevance one."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    fresh = await make_article(
        db_session, source, title="fresh", published_at=NOW
    )
    stale = await make_article(
        db_session, source, title="stale", published_at=NOW - timedelta(hours=72)
    )
    await set_relevance(db_session, fresh, user, 0.6)
    await set_relevance(db_session, stale, user, 0.6)
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None
    )
    assert [a.title for a in res.articles] == ["fresh", "stale"]


async def test_new_ignores_score_threshold(db_session, monkeypatch):
    """SCORE_THRESHOLD applies to the Feed, never to Explore."""
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.9")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")
    try:
        user = await make_user(db_session)
        source = await make_source(db_session, user)
        low = await make_article(db_session, source, title="low")
        await set_relevance(db_session, low, user, 0.1)
        await db_session.commit()

        res = await ExploreService(db_session).list_new(
            user.id, cursor=None, limit=None
        )
        assert [a.title for a in res.articles] == ["low"]
    finally:
        get_settings.cache_clear()


async def test_new_excludes_pending_articles(db_session):
    """Articles still awaiting enrichment must not surface."""
    from niouzou.models import Article
    from niouzou.models.article import STATUS_PENDING

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    enriched = await make_article(db_session, source, title="enriched")
    await set_relevance(db_session, enriched, user, 0.5)
    pending = Article(
        source_id=source.id,
        miniflux_entry_id=999_002,
        url="https://example.com/p",
        title="pending",
        status=STATUS_PENDING,
    )
    db_session.add(pending)
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None
    )
    assert [a.title for a in res.articles] == ["enriched"]


async def test_new_pagination_no_overlap(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(5):
        art = await make_article(
            db_session,
            source,
            title=f"a{i}",
            published_at=NOW - timedelta(hours=i),
        )
        await set_relevance(db_session, art, user, 0.5 + i * 0.05)
    await db_session.commit()

    svc = ExploreService(db_session)
    page1 = await svc.list_new(user.id, cursor=None, limit=2)
    assert page1.has_more is True
    page2 = await svc.list_new(user.id, cursor=page1.next_cursor, limit=2)
    page3 = await svc.list_new(user.id, cursor=page2.next_cursor, limit=2)

    ids = [a.id for p in (page1, page2, page3) for a in p.articles]
    assert len(ids) == len(set(ids)) == 5
    assert page3.has_more is False
