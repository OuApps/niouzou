"""E16-S3/S8 — Smart Match maths + dual-score ScoringService + nightly rescore.

All embeddings here are synthetic axis/blend vectors (tests/fake_embeddings.py)
so cosine similarities are exact: same axis → 1.0, different axes → 0.0,
blend → 0.7071 with each parent axis. The real model is never loaded.
DB-backed throughout (pgvector ``<=>`` is the unit under test); skips cleanly
without Postgres.
"""

import math
from datetime import datetime, timedelta, timezone

from niouzou.crons.nightly_refresh import rescore_recent
from niouzou.models import ArticleFeedback, ArticleRelevanceScore, KeywordWeight
from niouzou.scoring import ScoringPipeline, TFIDFScorer
from niouzou.scoring.smart_match import SmartMatchParams, smart_score
from niouzou.services.scoring_service import ScoringService
from tests.factories import add_keyword, make_article, make_source, make_user
from tests.fake_embeddings import axis_vector, blend_vector

PARAMS = SmartMatchParams()  # the documented defaults: k=5, λ=0.8, β=0.5, h=90


async def _embedded_article(session, source, vec, *, title="A", age_days=None):
    article = await make_article(session, source, title=title)
    article.embedding = vec
    if age_days is not None:
        article.created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    await session.flush()
    return article


async def _feedback(
    session,
    user,
    article,
    *,
    reaction="like",
    is_saved=False,
    read=False,
    age_days=0.0,
):
    ts = datetime.now(timezone.utc) - timedelta(days=age_days)
    session.add(
        ArticleFeedback(
            article_id=article.id,
            user_id=user.id,
            reaction=reaction,
            is_saved=is_saved,
            read_full_article=read,
            created_at=ts,
            updated_at=ts,
        )
    )
    await session.flush()


def _logit(score: float) -> float:
    return math.log(score / (1.0 - score))


# ── smart_score maths ─────────────────────────────────────────────────────────


async def test_likes_raise_close_candidates_and_ignore_orthogonal(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(3):
        liked = await _embedded_article(db_session, source, axis_vector(0), title=f"rugby {i}")
        await _feedback(db_session, user, liked)

    rugby = await _embedded_article(db_session, source, axis_vector(0), title="rugby new")
    bourse = await _embedded_article(db_session, source, axis_vector(1), title="bourse")

    rugby_score, rugby_cold = await smart_score(
        db_session, rugby.id, user.id, params=PARAMS
    )
    bourse_score, bourse_cold = await smart_score(
        db_session, bourse.id, user.id, params=PARAMS
    )

    assert rugby_score > 0.5
    # Orthogonal candidate: no relevant neighbour → neutral, NOT penalised.
    assert abs(bourse_score - 0.5) < 1e-6
    assert rugby_cold is False and bourse_cold is False


async def test_multi_interest_clusters_no_centroid_effect(db_session):
    """Two orthogonal like-clusters must both win, and a halfway candidate
    must not beat either — the k-NN judges each candidate against its own
    cluster, never against an averaged profile."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(3):
        rugby = await _embedded_article(db_session, source, axis_vector(0), title=f"rugby {i}")
        await _feedback(db_session, user, rugby)
        tech = await _embedded_article(db_session, source, axis_vector(1), title=f"tech {i}")
        await _feedback(db_session, user, tech)

    # k = cluster size so each candidate is judged against one full cluster.
    params = SmartMatchParams(topk=3)
    cand_rugby = await _embedded_article(db_session, source, axis_vector(0), title="r cand")
    cand_tech = await _embedded_article(db_session, source, axis_vector(1), title="t cand")
    cand_mid = await _embedded_article(db_session, source, blend_vector(0, 1), title="mid cand")

    s_rugby, _ = await smart_score(db_session, cand_rugby.id, user.id, params=params)
    s_tech, _ = await smart_score(db_session, cand_tech.id, user.id, params=params)
    s_mid, _ = await smart_score(db_session, cand_mid.id, user.id, params=params)

    assert s_rugby > 0.5 and s_tech > 0.5
    assert s_mid <= s_rugby and s_mid <= s_tech


async def test_dislikes_push_close_candidates_below_neutral(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(2):
        disliked = await _embedded_article(db_session, source, axis_vector(0), title=f"d{i}")
        await _feedback(db_session, user, disliked, reaction="dislike")
    # One unrelated like so the user isn't cold.
    liked = await _embedded_article(db_session, source, axis_vector(5), title="liked")
    await _feedback(db_session, user, liked)

    candidate = await _embedded_article(db_session, source, axis_vector(0), title="cand")
    score, is_cold = await smart_score(db_session, candidate.id, user.id, params=PARAMS)

    assert score < 0.5
    assert is_cold is False


async def test_decay_halves_twice_at_double_halflife(db_session):
    """A like aged 2×halflife contributes 4× less raw signal than a fresh one."""
    user_fresh = await make_user(db_session, email="fresh@test.dev")
    user_old = await make_user(db_session, email="old@test.dev")
    src_fresh = await make_source(db_session, user_fresh, feed_id=1)
    src_old = await make_source(db_session, user_old, feed_id=2)

    fresh_like = await _embedded_article(db_session, src_fresh, axis_vector(0), title="f")
    await _feedback(db_session, user_fresh, fresh_like, age_days=0.0)
    old_like = await _embedded_article(db_session, src_old, axis_vector(0), title="o")
    await _feedback(
        db_session, user_old, old_like, age_days=2 * PARAMS.decay_halflife_days
    )

    cand_fresh = await _embedded_article(db_session, src_fresh, axis_vector(0), title="cf")
    cand_old = await _embedded_article(db_session, src_old, axis_vector(0), title="co")

    s_fresh, _ = await smart_score(db_session, cand_fresh.id, user_fresh.id, params=PARAMS)
    s_old, _ = await smart_score(db_session, cand_old.id, user_old.id, params=PARAMS)

    # logit(score) = β·raw, so the raw ratio is recoverable exactly.
    raw_fresh = _logit(s_fresh) / PARAMS.beta
    raw_old = _logit(s_old) / PARAMS.beta
    assert abs(raw_fresh - 1.0) < 0.01  # sim 1 × value 1 × decay(0) = 1
    assert abs(raw_fresh / raw_old - 4.0) < 0.05


async def test_user_without_feedback_is_neutral_and_cold(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    candidate = await _embedded_article(db_session, source, axis_vector(0))

    score, is_cold = await smart_score(db_session, candidate.id, user.id, params=PARAMS)

    assert abs(score - 0.5) < 1e-9
    assert is_cold is True


async def test_feedback_value_uses_saved_and_read_dimensions(db_session):
    """value = reaction ± 1 + 0.5·saved + 0.5·read (E9-S1) — a save+read with
    no reaction is positive signal."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    saved = await _embedded_article(db_session, source, axis_vector(0))
    await _feedback(db_session, user, saved, reaction="none", is_saved=True, read=True)

    candidate = await _embedded_article(db_session, source, axis_vector(0), title="cand")
    score, is_cold = await smart_score(db_session, candidate.id, user.id, params=PARAMS)

    assert score > 0.5
    assert is_cold is False


# ── ScoringService — both scores at once (E16-S8) ────────────────────────────


def _service() -> ScoringService:
    return ScoringService(
        ScoringPipeline(TFIDFScorer()),
        max_keywords_per_article=6,
        smart_params=PARAMS,
    )


async def test_scoring_populates_both_columns(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await _embedded_article(db_session, source, axis_vector(0))
    await add_keyword(db_session, article, "rugby", 0.9)

    await _service().score_article_for_user(db_session, article.id, user.id)

    row = await db_session.get(ArticleRelevanceScore, (article.id, user.id))
    assert row.keyword_score is not None
    assert row.smart_score is not None
    assert row.smart_cold_start is True  # no positive feedback yet
    assert row.keyword_cold_start is True  # no keyword in the user's vocab


async def test_article_without_embedding_scores_keyword_only(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)  # embedding stays NULL
    await add_keyword(db_session, article, "rugby", 0.9)

    await _service().score_article_for_user(db_session, article.id, user.id)

    row = await db_session.get(ArticleRelevanceScore, (article.id, user.id))
    assert row.smart_score is None
    assert row.keyword_score is not None and 0.0 <= row.keyword_score <= 1.0


async def test_article_without_keywords_scores_smart_only(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await _embedded_article(db_session, source, axis_vector(0))

    await _service().score_article_for_user(db_session, article.id, user.id)

    row = await db_session.get(ArticleRelevanceScore, (article.id, user.id))
    assert row.keyword_score is None
    assert row.smart_score is not None


# ── nightly rescoring (E16-S3, dual since E16-S9) ─────────────────────────────


async def test_rescore_lifts_frozen_neutral_score_after_likes(db_session):
    """The frozen-score fix: a 0.5 stamped before the user had any history
    rises once the user likes similar articles — whatever scoring_mode says
    (no override set here: the rescore no longer gates on the mode)."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    candidate = await _embedded_article(db_session, source, axis_vector(0))
    db_session.add(
        ArticleRelevanceScore(
            article_id=candidate.id,
            user_id=user.id,
            smart_score=0.5,
            smart_cold_start=True,
        )
    )
    for i in range(3):
        liked = await _embedded_article(db_session, source, axis_vector(0), title=f"l{i}")
        await _feedback(db_session, user, liked)
    await db_session.flush()

    rescored = await rescore_recent(db_session)
    assert rescored >= 1

    row = await db_session.get(ArticleRelevanceScore, (candidate.id, user.id))
    await db_session.refresh(row)
    assert row.smart_score > 0.5
    assert row.smart_cold_start is False


async def test_rescore_refreshes_keyword_score_too(db_session):
    """E16-S9 — the nightly pass refreshes BOTH columns: a stale neutral
    keyword_score follows the recomputed weights."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rugby", 0.9)
    db_session.add(
        ArticleRelevanceScore(
            article_id=article.id,
            user_id=user.id,
            keyword_score=0.5,
            keyword_cold_start=True,
        )
    )
    db_session.add(
        KeywordWeight(
            user_id=user.id, term="rugby", weight=3.0, manually_overridden=False
        )
    )
    await db_session.flush()

    assert await rescore_recent(db_session) >= 1

    row = await db_session.get(ArticleRelevanceScore, (article.id, user.id))
    await db_session.refresh(row)
    assert row.keyword_score > 0.5
    assert row.keyword_cold_start is False


async def test_rescore_only_touches_the_recent_window(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    # Ingested well outside smart_rescore_window_days (default 14).
    stale = await _embedded_article(db_session, source, axis_vector(0), age_days=60)
    db_session.add(
        ArticleRelevanceScore(
            article_id=stale.id, user_id=user.id, smart_score=0.5
        )
    )
    liked = await _embedded_article(db_session, source, axis_vector(0), title="l")
    await _feedback(db_session, user, liked)
    await db_session.flush()

    await rescore_recent(db_session)

    row = await db_session.get(ArticleRelevanceScore, (stale.id, user.id))
    await db_session.refresh(row)
    # Outside the window → frozen, even though a like would now lift it.
    assert row.smart_score == 0.5


# ── E16-S5 — pinned keywords as hard boosts ───────────────────────────────────


async def _pin(session, user, term, weight):
    session.add(
        KeywordWeight(
            user_id=user.id, term=term, weight=weight, manually_overridden=True
        )
    )
    await session.flush()


async def test_positive_pin_boosts_article_without_any_like(db_session):
    """Pin 'rugby' at +5 → any article carrying the keyword wins the boost,
    even though the user has zero like history (the user contract)."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await _embedded_article(db_session, source, axis_vector(0))
    await add_keyword(db_session, article, "rugby", 0.9)
    await _pin(db_session, user, "rugby", 5.0)

    score, _ = await smart_score(db_session, article.id, user.id, params=PARAMS)

    # sigmoid(0 + 5·0.9) ≈ 0.989 — way above neutral.
    assert score > 0.95


async def test_negative_pin_pushes_article_below_neutral(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await _embedded_article(db_session, source, axis_vector(0))
    await add_keyword(db_session, article, "politique", 0.8)
    await _pin(db_session, user, "politique", -5.0)

    score, _ = await smart_score(db_session, article.id, user.id, params=PARAMS)

    assert score < 0.05


async def test_learned_weights_do_not_boost_in_smart_mode(db_session):
    """Only *pinned* (manually_overridden) weights act on the smart score —
    learned weights are indicative, the embedding carries the signal."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await _embedded_article(db_session, source, axis_vector(0))
    await add_keyword(db_session, article, "rugby", 0.9)
    db_session.add(
        KeywordWeight(
            user_id=user.id, term="rugby", weight=5.0, manually_overridden=False
        )
    )
    await db_session.flush()

    score, _ = await smart_score(db_session, article.id, user.id, params=PARAMS)

    assert abs(score - 0.5) < 1e-9


async def test_pin_only_applies_to_articles_carrying_the_keyword(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    await _pin(db_session, user, "rugby", 5.0)
    other = await _embedded_article(db_session, source, axis_vector(1))
    await add_keyword(db_session, other, "bourse", 0.9)

    score, _ = await smart_score(db_session, other.id, user.id, params=PARAMS)

    assert abs(score - 0.5) < 1e-9


# ── E16-S7/S10 — score-debug breakdown, both sections at once ─────────────────


async def test_score_debug_returns_both_sections(db_session):
    from niouzou.services.articles_service import ArticlesService

    user = await make_user(db_session)
    source = await make_source(db_session, user)

    fresh_like = await _embedded_article(db_session, source, axis_vector(0), title="fresh like")
    await _feedback(db_session, user, fresh_like, age_days=0.0)
    old_like = await _embedded_article(db_session, source, axis_vector(0), title="old like")
    await _feedback(db_session, user, old_like, age_days=PARAMS.decay_halflife_days)
    dislike = await _embedded_article(db_session, source, axis_vector(0), title="disliked")
    await _feedback(db_session, user, dislike, reaction="dislike")

    candidate = await _embedded_article(db_session, source, axis_vector(0), title="candidate")
    await add_keyword(db_session, candidate, "rugby", 0.9)
    await _pin(db_session, user, "rugby", 5.0)
    db_session.add(
        ArticleRelevanceScore(
            article_id=candidate.id,
            user_id=user.id,
            keyword_score=0.6,
            smart_score=0.9,
        )
    )
    await db_session.flush()

    debug = await ArticlesService(db_session).score_debug(user.id, candidate.id)

    # Both persisted scores travel together (E16-S10).
    assert debug.keyword_score == 0.6
    assert debug.smart_score == 0.9
    assert debug.active_method == "keyword"  # the default mode
    liked = {n.title: n for n in debug.liked_neighbors}
    assert set(liked) == {"fresh like", "old like"}
    assert all(abs(n.similarity - 1.0) < 1e-6 for n in liked.values())
    # Decay: the halflife-old like contributes half the fresh one.
    assert abs(liked["fresh like"].contribution - 1.0) < 0.01
    assert abs(liked["old like"].contribution - 0.5) < 0.01
    assert [n.title for n in debug.disliked_neighbors] == ["disliked"]
    assert len(debug.pins) == 1
    pin = debug.pins[0]
    assert (pin.term, pin.weight, pin.salience) == ("rugby", 5.0, 0.9)
    assert abs(pin.contribution - 4.5) < 1e-9
    # Keyword section: the pinned weight shows on the article's keyword list.
    assert [kw.term for kw in debug.keywords] == ["rugby"]


async def test_score_debug_without_embedding_degrades_cleanly(db_session):
    from niouzou.services.articles_service import ArticlesService

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)  # embedding NULL
    await add_keyword(db_session, article, "rust", 0.9)
    db_session.add(
        ArticleRelevanceScore(
            article_id=article.id,
            user_id=user.id,
            keyword_score=0.6,
        )
    )
    await db_session.flush()

    debug = await ArticlesService(db_session).score_debug(user.id, article.id)

    assert debug.keyword_score == 0.6
    assert debug.smart_score is None
    assert debug.liked_neighbors == []
    assert debug.disliked_neighbors == []
    assert debug.pins == []
    assert [kw.term for kw in debug.keywords] == ["rust"]
