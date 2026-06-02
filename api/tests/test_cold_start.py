"""Cold-start flag end-to-end (E10-S4).

Covers:
- ScoringService stamps ``is_cold_start`` when none of the article's keywords
  has a row in ``keyword_weights`` for the user, and unsets it when at least
  one does.
- ``cron_refresh_weights.demote_cold_flags`` flips stale cold rows once a
  feedback brings a keyword into the user's vocab.
- ``FeedService`` passes cold articles through even with a high
  ``score_threshold``, and ``ranked_query`` projects ``is_cold_start`` to
  the response payload.
"""

import uuid

from sqlalchemy import select

from niouzou.config import get_settings
from niouzou.models import (
    ArticleFeedback,
    ArticleImpression,
    ArticleRelevanceScore,
    KeywordWeight,
)
from niouzou.scoring import ScoringPipeline, TFIDFScorer
from niouzou.services.feed_service import FeedService
from niouzou.services.scoring_service import ScoringService
from niouzou.services.weights import demote_cold_flags
from tests.factories import (
    add_keyword,
    make_article,
    make_source,
    make_user,
    set_relevance,
)


def _scoring() -> ScoringService:
    return ScoringService(ScoringPipeline(TFIDFScorer()))


async def _score(
    db_session, article_id: uuid.UUID, user_id: uuid.UUID
) -> ArticleRelevanceScore:
    """Run scoring + return the persisted row."""
    await _scoring().score_article_for_user(db_session, article_id, user_id)
    return (
        await db_session.execute(
            select(ArticleRelevanceScore).where(
                ArticleRelevanceScore.article_id == article_id,
                ArticleRelevanceScore.user_id == user_id,
            )
        )
    ).scalar_one()


# ── Scoring stamps is_cold_start ────────────────────────────────────────────


async def test_scoring_stamps_cold_when_no_keyword_known(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "fc barcelone", 0.9)
    await add_keyword(db_session, article, "ligue des champions", 0.7)
    await db_session.commit()

    row = await _score(db_session, article.id, user.id)
    assert row.is_cold_start is True


async def test_scoring_stamps_warm_when_at_least_one_known(db_session):
    """Strict criterion: a single known keyword (even with zero-ish weight)
    flips the article out of cold-start. Mirrors the spec's "any signal
    counts" rule — a user who pinned ``football`` to 0 has *stated* an
    opinion."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "football", 0.9)
    await add_keyword(db_session, article, "fc barcelone", 0.7)
    db_session.add(
        KeywordWeight(user_id=user.id, term="football", weight=0.0001)
    )
    await db_session.commit()

    row = await _score(db_session, article.id, user.id)
    assert row.is_cold_start is False


# ── demote_cold_flags (cron pass) ───────────────────────────────────────────


async def test_demote_flips_only_rows_whose_keywords_acquired_weight(
    db_session,
):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    cold_kept = await make_article(db_session, source, title="kept cold")
    cold_demoted = await make_article(db_session, source, title="becomes warm")
    await add_keyword(db_session, cold_kept, "rust", 0.9)
    await add_keyword(db_session, cold_demoted, "football", 0.9)
    await db_session.commit()

    # Both rows start cold.
    await _score(db_session, cold_kept.id, user.id)
    await _score(db_session, cold_demoted.id, user.id)

    # User feedbacks something on ``football`` → weight row appears, the
    # ``becomes warm`` article must be demoted on the next nightly pass.
    db_session.add(
        KeywordWeight(user_id=user.id, term="football", weight=0.5)
    )
    await db_session.commit()

    rowcount = await demote_cold_flags(db_session)
    await db_session.commit()

    assert rowcount == 1
    kept = await db_session.get(
        ArticleRelevanceScore, (cold_kept.id, user.id)
    )
    demoted = await db_session.get(
        ArticleRelevanceScore, (cold_demoted.id, user.id)
    )
    assert kept.is_cold_start is True
    assert demoted.is_cold_start is False


async def test_demote_is_noop_when_nothing_to_flip(db_session):
    """No cold rows → returns 0 and doesn't mutate the table."""
    rowcount = await demote_cold_flags(db_session)
    await db_session.commit()
    assert rowcount == 0


# ── FeedService bypass + projection ─────────────────────────────────────────


async def test_feed_returns_cold_articles_above_threshold(db_session, monkeypatch):
    """A cold article with a low raw score still surfaces when threshold is
    high — that's the only way the user can ever feedback its keywords.

    The E7-S6 cold-start gate is its own thing (user has fewer than N
    feedbacks → ignore threshold entirely). We graduate the user out of it
    via a couple of feedbacks on unrelated articles so this test exercises
    the **per-article** cold flag, not the per-user one.
    """
    get_settings.cache_clear()
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")  # remove noise
    monkeypatch.setenv("COLD_START_THRESHOLD", "2")
    try:
        user = await make_user(db_session)
        source = await make_source(db_session, user)
        cold_article = await make_article(db_session, source, title="cold")
        warm_low = await make_article(db_session, source, title="warm low")
        await add_keyword(db_session, cold_article, "rust", 0.9)
        await add_keyword(db_session, warm_low, "politics", 0.9)
        db_session.add(
            KeywordWeight(user_id=user.id, term="politics", weight=0.0)
        )
        # Stamp explicit scores rather than computing via the pipeline so the
        # test's intent (threshold bypass) doesn't depend on TF-IDF heuristics.
        db_session.add(
            ArticleRelevanceScore(
                article_id=cold_article.id,
                user_id=user.id,
                relevance_score=0.30,
                is_cold_start=True,
            )
        )
        db_session.add(
            ArticleRelevanceScore(
                article_id=warm_low.id,
                user_id=user.id,
                relevance_score=0.30,
                is_cold_start=False,
            )
        )
        # Two feedbacks on unrelated already-seen articles take the user out
        # of E7-S6 cold-start so the threshold actually applies.
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

        page = await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None, min_score=0.9
        )
        ids = [a.id for a in page.articles]
        # cold passes, warm-but-low does not.
        assert cold_article.id in ids
        assert warm_low.id not in ids
        cold_in_response = next(a for a in page.articles if a.id == cold_article.id)
        assert cold_in_response.is_cold_start is True
    finally:
        get_settings.cache_clear()
