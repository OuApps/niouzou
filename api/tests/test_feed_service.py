"""Feed endpoint tests (E3-S5): ranking, impression exclusion, cursor paging."""

from datetime import datetime, timedelta, timezone

from niouzou.config import get_settings
from niouzou.models import ArticleFeedback, ArticleImpression
from niouzou.services.feed_service import FeedService
from niouzou.services.settings_service import SettingsService
from tests.factories import make_article, make_source, make_user, set_relevance

NOW = datetime.now(timezone.utc)


async def test_higher_feed_rank_comes_first(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    low = await make_article(db_session, source, title="low", published_at=NOW)
    high = await make_article(db_session, source, title="high", published_at=NOW)
    await set_relevance(db_session, low, user, 0.1)
    await set_relevance(db_session, high, user, 0.9)
    await db_session.commit()

    feed = await FeedService(db_session).get_feed(user.id, cursor=None, limit=None)

    assert [a.title for a in feed.articles] == ["high", "low"]
    assert feed.has_more is False


async def test_seen_articles_are_excluded(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    seen = await make_article(db_session, source, title="seen")
    fresh = await make_article(db_session, source, title="fresh")
    await set_relevance(db_session, seen, user, 0.8)
    await set_relevance(db_session, fresh, user, 0.8)
    db_session.add(ArticleImpression(article_id=seen.id, user_id=user.id))
    await db_session.commit()

    feed = await FeedService(db_session).get_feed(user.id, cursor=None, limit=None)

    assert [a.title for a in feed.articles] == ["fresh"]


async def test_only_own_sources_appear(db_session):
    user = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    mine = await make_source(db_session, user, feed_id=1)
    theirs = await make_source(db_session, other, feed_id=2)
    a_mine = await make_article(db_session, mine, title="mine")
    a_theirs = await make_article(db_session, theirs, title="theirs")
    await set_relevance(db_session, a_mine, user, 0.5)
    await set_relevance(db_session, a_theirs, other, 0.9)
    await db_session.commit()

    feed = await FeedService(db_session).get_feed(user.id, cursor=None, limit=None)

    assert [a.title for a in feed.articles] == ["mine"]


async def test_cursor_pages_do_not_overlap(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    # Distinct relevance → distinct, stable feed_rank ordering.
    for i in range(5):
        art = await make_article(
            db_session, source, title=f"a{i}", published_at=NOW - timedelta(hours=i)
        )
        await set_relevance(db_session, art, user, 0.5 + i * 0.1)
    await db_session.commit()

    svc = FeedService(db_session)
    page1 = await svc.get_feed(user.id, cursor=None, limit=2)
    assert page1.has_more is True
    assert len(page1.articles) == 2

    page2 = await svc.get_feed(user.id, cursor=page1.next_cursor, limit=2)
    assert len(page2.articles) == 2

    page3 = await svc.get_feed(user.id, cursor=page2.next_cursor, limit=2)
    assert len(page3.articles) == 1
    assert page3.has_more is False

    seen_ids = [a.id for a in page1.articles + page2.articles + page3.articles]
    assert len(seen_ids) == len(set(seen_ids)) == 5


async def test_scoring_mode_flip_reranks_without_rescore(db_session):
    """E16-S9 — scoring_mode selects the active score column; flipping it
    re-ranks instantly using the other persisted column, no DB write."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    a = await make_article(db_session, source, title="keyword-wins", published_at=NOW)
    b = await make_article(db_session, source, title="smart-wins", published_at=NOW)
    await set_relevance(db_session, a, user, 0.9, smart_score=0.1)
    await set_relevance(db_session, b, user, 0.1, smart_score=0.9)
    await db_session.commit()

    svc = FeedService(db_session)
    feed = await svc.get_feed(user.id, cursor=None, limit=None)
    assert [x.title for x in feed.articles] == ["keyword-wins", "smart-wins"]
    assert feed.articles[0].active_method == "keyword"
    # Both scores travel in every row (E16-S10).
    assert feed.articles[0].keyword_score == 0.9
    assert feed.articles[0].smart_score == 0.1

    await SettingsService(db_session).set("scoring_mode", "smart")
    await db_session.commit()

    feed = await svc.get_feed(user.id, cursor=None, limit=None)
    assert [x.title for x in feed.articles] == ["smart-wins", "keyword-wins"]
    assert feed.articles[0].active_method == "smart"


async def test_null_active_score_is_treated_as_cold(db_session, monkeypatch):
    """E16-S9 — a NULL active score (method had no input) surfaces with the
    0.5 baseline and bypasses the threshold instead of being hidden."""
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.8")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")
    monkeypatch.setenv("COLD_START_THRESHOLD", "1")

    try:
        user = await make_user(db_session)
        source = await make_source(db_session, user)
        unscored = await make_article(db_session, source, title="no-keywords")
        await set_relevance(db_session, unscored, user, None, smart_score=0.9)
        # One feedback graduates the user out of the E7-S6 global cold start,
        # so the threshold actually applies.
        seen = await make_article(db_session, source, title="seen")
        await set_relevance(db_session, seen, user, 0.9)
        db_session.add(ArticleImpression(article_id=seen.id, user_id=user.id))
        db_session.add(
            ArticleFeedback(article_id=seen.id, user_id=user.id, reaction="like")
        )
        await db_session.commit()

        feed = await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None
        )

        assert [a.title for a in feed.articles] == ["no-keywords"]
        assert feed.articles[0].keyword_score is None
    finally:
        get_settings.cache_clear()


async def test_cold_start_bypasses_score_threshold(db_session, monkeypatch):
    """E7-S6: a new user with no feedback sees sub-threshold articles."""
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.8")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")

    try:
        user = await make_user(db_session)
        source = await make_source(db_session, user)
        art = await make_article(db_session, source, title="low-score")
        await set_relevance(db_session, art, user, 0.2)
        await db_session.commit()

        feed = await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None
        )

        assert [a.title for a in feed.articles] == ["low-score"]
        assert feed.cold_start is True
    finally:
        get_settings.cache_clear()


async def test_cold_start_ends_after_threshold_reached(db_session, monkeypatch):
    """E7-S6: once COLD_START_THRESHOLD feedbacks are in, the floor applies."""
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.8")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")
    monkeypatch.setenv("COLD_START_THRESHOLD", "2")

    try:
        user = await make_user(db_session)
        source = await make_source(db_session, user)
        low = await make_article(db_session, source, title="low")
        await set_relevance(db_session, low, user, 0.2)
        # Two feedbacks on unrelated articles graduates the user out of cold
        # start.
        for i in range(2):
            other = await make_article(db_session, source, title=f"seen-{i}")
            await set_relevance(db_session, other, user, 0.2)
            db_session.add(
                ArticleImpression(article_id=other.id, user_id=user.id)
            )
            db_session.add(
                ArticleFeedback(
                    article_id=other.id, user_id=user.id, reaction="like"
                )
            )
        await db_session.commit()

        feed = await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None
        )

        assert feed.cold_start is False
        assert feed.articles == []
    finally:
        get_settings.cache_clear()
