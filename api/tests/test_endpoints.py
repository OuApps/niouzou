"""Service tests for the remaining read endpoints (E3-S7).

Covers article detail, saved list, and keyword listing/override.
"""

import pytest

from niouzou.errors import APIError
from niouzou.services.articles_service import ArticlesService
from niouzou.services.feedback_service import FeedbackService
from niouzou.services.keywords_service import KeywordsService
from niouzou.services.saved_service import SavedService
from tests.factories import (
    add_keyword,
    make_article,
    make_source,
    make_user,
    set_relevance,
)


async def test_article_detail_shape(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, title="Why Rust")
    await set_relevance(db_session, article, user, 0.87)
    await db_session.commit()

    detail = await ArticlesService(db_session).get(user.id, article.id)
    assert detail.title == "Why Rust"
    assert detail.relevance_score == 0.87
    assert detail.source.name == "Feed"
    assert detail.feedback is None  # no interaction yet


async def test_article_detail_includes_feedback_after_action(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await db_session.commit()

    await FeedbackService(db_session).record(user.id, article.id, "like")
    await db_session.commit()

    detail = await ArticlesService(db_session).get(user.id, article.id)
    assert detail.feedback is not None
    assert detail.feedback.action == "like"


async def test_article_of_another_user_is_not_found(db_session):
    owner = await make_user(db_session, email="owner@test.dev")
    intruder = await make_user(db_session, email="intruder@test.dev")
    source = await make_source(db_session, owner)
    article = await make_article(db_session, source)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await ArticlesService(db_session).get(intruder.id, article.id)
    assert exc.value.status_code == 404


async def test_feedback_on_foreign_article_404(db_session):
    owner = await make_user(db_session, email="o@test.dev")
    intruder = await make_user(db_session, email="i@test.dev")
    source = await make_source(db_session, owner)
    article = await make_article(db_session, source)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await FeedbackService(db_session).record(intruder.id, article.id, "like")
    assert exc.value.status_code == 404


async def test_saved_lists_only_saved_newest_first(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    a1 = await make_article(db_session, source, title="first")
    a2 = await make_article(db_session, source, title="second")
    liked = await make_article(db_session, source, title="liked-not-saved")
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(user.id, a1.id, "save")
    await db_session.commit()
    await svc.record(user.id, a2.id, "save")
    await db_session.commit()
    await svc.record(user.id, liked.id, "like")
    await db_session.commit()

    saved = await SavedService(db_session).list_saved(user.id, cursor=None, limit=None)
    titles = [a.title for a in saved.articles]
    assert "liked-not-saved" not in titles
    assert titles == ["second", "first"]  # newest save first


async def test_keywords_listed_by_absolute_weight(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.9)
    await add_keyword(db_session, article, "php", 0.2)
    await db_session.commit()

    await FeedbackService(db_session).record(user.id, article.id, "dislike")
    await db_session.commit()

    listed = await KeywordsService(db_session).list_keywords(
        user.id, cursor=None, limit=None
    )
    # Both negative; rust has larger |weight| so it comes first.
    assert [k.term for k in listed.keywords] == ["rust", "php"]


async def test_patch_keyword_overrides_and_pins(db_session):
    user = await make_user(db_session)
    await db_session.commit()

    svc = KeywordsService(db_session)
    out = await svc.set_weight(user.id, "rust", 0.0)
    await db_session.commit()

    assert out.term == "rust"
    assert out.weight == 0.0
    # Re-running listing reflects the override.
    listed = await svc.list_keywords(user.id, cursor=None, limit=None)
    assert listed.keywords[0].term == "rust"
