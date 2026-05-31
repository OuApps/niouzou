"""E9-S1 canonical scoring formula — exact-value assertions.

contribution = salience × (
    +1 if reaction='like' / -1 if reaction='dislike' / 0 otherwise
  + 0.5 if is_saved
  + 0.5 if read_full_article
)
"""

from sqlalchemy import select

from niouzou.models import KeywordWeight
from niouzou.services.feedback_service import FeedbackService
from tests.factories import (
    add_keyword,
    feedback_request,
    make_article,
    make_source,
    make_user,
)

# All keywords share salience 1.0 so contributions equal the signal magnitude.
_SALIENCE = 1.0


async def _weight(session, user, term: str) -> float:
    row = await session.scalar(
        select(KeywordWeight).where(
            KeywordWeight.user_id == user.id, KeywordWeight.term == term
        )
    )
    return row.weight if row is not None else 0.0


async def _seed(db_session, term: str = "rust"):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, term, _SALIENCE)
    await db_session.commit()
    return user, article


async def test_like_alone(db_session):
    user, article = await _seed(db_session)
    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, reaction="like")
    )
    await db_session.commit()
    assert await _weight(db_session, user, "rust") == 1.0


async def test_like_and_save(db_session):
    user, article = await _seed(db_session)
    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, reaction="like", is_saved=True)
    )
    await db_session.commit()
    assert await _weight(db_session, user, "rust") == 1.5


async def test_like_and_read(db_session):
    user, article = await _seed(db_session)
    await FeedbackService(db_session).record(
        user.id,
        feedback_request(article.id, reaction="like", read_full_article=True),
    )
    await db_session.commit()
    assert await _weight(db_session, user, "rust") == 1.5


async def test_like_save_and_read(db_session):
    user, article = await _seed(db_session)
    await FeedbackService(db_session).record(
        user.id,
        feedback_request(
            article.id,
            reaction="like",
            is_saved=True,
            read_full_article=True,
        ),
    )
    await db_session.commit()
    assert await _weight(db_session, user, "rust") == 2.0


async def test_dislike_alone(db_session):
    user, article = await _seed(db_session)
    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, reaction="dislike")
    )
    await db_session.commit()
    assert await _weight(db_session, user, "rust") == -1.0


async def test_dislike_and_save(db_session):
    """The 'odd-but-legal' case: keep for reference, disagree with content."""
    user, article = await _seed(db_session)
    await FeedbackService(db_session).record(
        user.id,
        feedback_request(article.id, reaction="dislike", is_saved=True),
    )
    await db_session.commit()
    assert await _weight(db_session, user, "rust") == -0.5


async def test_neutral_row_contributes_zero(db_session):
    """An is_saved=False / read=False row exists (somehow) and must contribute 0."""
    user, article = await _seed(db_session)
    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, is_saved=True)
    )
    await db_session.commit()
    # First the +0.5 from save:
    assert await _weight(db_session, user, "rust") == 0.5

    # Un-saving brings the weight back to 0.
    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, is_saved=False)
    )
    await db_session.commit()
    assert await _weight(db_session, user, "rust") == 0.0


async def test_like_saved_outweighs_like_alone(db_session):
    """Acceptance criterion: a liked + saved keyword > a liked-only keyword."""
    user, article = await _seed(db_session)
    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, reaction="like")
    )
    await db_session.commit()
    liked_only = await _weight(db_session, user, "rust")

    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, is_saved=True)
    )
    await db_session.commit()
    liked_and_saved = await _weight(db_session, user, "rust")

    assert liked_and_saved > liked_only
    assert liked_and_saved == 1.5
    assert liked_only == 1.0
