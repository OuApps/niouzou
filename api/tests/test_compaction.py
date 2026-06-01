"""Tests for keyword compaction (E10-S3)."""

import pytest
from sqlalchemy import select

from niouzou.models import ArticleKeyword, CompactionRun, KeywordWeight
from niouzou.models.compaction_run import (
    STATUS_APPLIED,
    STATUS_PREVIEW,
    STATUS_REJECTED,
)
from niouzou.services.compaction_service import (
    CompactionService,
    _parse_groups,
)
from tests.factories import (
    add_keyword,
    make_article,
    make_source,
    make_user,
)
from tests.test_ai_keyword import FakeClient


# ── _parse_groups (unit) ────────────────────────────────────────────────────


def test_parse_groups_basic():
    groups = _parse_groups(
        {
            "groups": [
                {"canonical": "FC Barcelone", "aliases": ["Barça", "Barcelona FC"]}
            ]
        }
    )
    assert len(groups) == 1
    g = groups[0]
    # Lowercased + dedup against canonical.
    assert g.canonical == "fc barcelone"
    assert g.aliases == ["barça", "barcelona fc"]


def test_parse_groups_skips_singletons_and_invalid():
    groups = _parse_groups(
        {
            "groups": [
                {"canonical": "psg", "aliases": []},  # singleton dropped
                {"canonical": "om", "aliases": ["om", "olympique de marseille"]},
                "garbage",  # not a dict
                {"canonical": "asse", "aliases": [None, 123, ""]},  # all invalid
            ]
        }
    )
    # Only the OM group survives — aliases contained canonical so it's deduped,
    # leaving one real alias.
    assert [(g.canonical, g.aliases) for g in groups] == [
        ("om", ["olympique de marseille"])
    ]


# ── apply (DB-backed) ───────────────────────────────────────────────────────


async def test_apply_renames_aliases_and_recomputes_weights(db_session):
    """Aliases on ``article_keywords`` get renamed; weights rebuild."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    a1 = await make_article(db_session, source, title="match")
    a2 = await make_article(db_session, source, title="report")
    await add_keyword(db_session, a1, "fc barcelone", 0.9)
    await add_keyword(db_session, a2, "barça", 0.8)
    await db_session.commit()

    # Pre-seed a preview row directly (skip the LLM hop in the test).
    run = CompactionRun(
        status=STATUS_PREVIEW,
        groups_json=[
            {"canonical": "fc barcelone", "aliases": ["barça"]}
        ],
    )
    db_session.add(run)
    await db_session.commit()

    svc = CompactionService(db_session)
    await svc.apply(run.id)
    await db_session.commit()

    # Both articles now point at the canonical term.
    terms = (
        await db_session.execute(select(ArticleKeyword.term).order_by(ArticleKeyword.term))
    ).scalars().all()
    assert terms == ["fc barcelone", "fc barcelone"]

    refreshed = await db_session.get(CompactionRun, run.id)
    assert refreshed.status == STATUS_APPLIED
    assert refreshed.applied_at is not None
    assert refreshed.keywords_merged == 1


async def test_apply_skips_pinned_groups(db_session):
    """A pinned alias keeps the whole group from being merged silently."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    a1 = await make_article(db_session, source)
    await add_keyword(db_session, a1, "barça", 0.5)
    # User has explicitly tuned ``barça`` — must not be silently renamed.
    db_session.add(
        KeywordWeight(
            user_id=user.id, term="barça", weight=2.0, manually_overridden=True
        )
    )
    await db_session.commit()

    run = CompactionRun(
        status=STATUS_PREVIEW,
        groups_json=[
            {"canonical": "fc barcelone", "aliases": ["barça"]}
        ],
    )
    db_session.add(run)
    await db_session.commit()

    await CompactionService(db_session).apply(run.id)
    await db_session.commit()

    # Term untouched.
    terms = (
        await db_session.execute(select(ArticleKeyword.term))
    ).scalars().all()
    assert terms == ["barça"]

    refreshed = await db_session.get(CompactionRun, run.id)
    assert refreshed.status == STATUS_APPLIED
    # Group annotated for the admin UI.
    assert refreshed.groups_json[0]["skipped_reason"] == "pinned"
    assert refreshed.keywords_merged == 0


async def test_apply_resolves_pk_collisions(db_session):
    """An article carrying both canonical + alias collapses to MAX(salience)."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    # Same article, both forms — UPDATE would violate (article_id, term) PK
    # without the pre-collapse step.
    await add_keyword(db_session, article, "fc barcelone", 0.6)
    await add_keyword(db_session, article, "barça", 0.9)
    await db_session.commit()

    run = CompactionRun(
        status=STATUS_PREVIEW,
        groups_json=[
            {"canonical": "fc barcelone", "aliases": ["barça"]}
        ],
    )
    db_session.add(run)
    await db_session.commit()

    await CompactionService(db_session).apply(run.id)
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(ArticleKeyword.term, ArticleKeyword.salience).where(
                ArticleKeyword.article_id == article.id
            )
        )
    ).all()
    # One row, salience kept = MAX(0.6, 0.9) = 0.9.
    assert [(r.term, r.salience) for r in rows] == [("fc barcelone", 0.9)]


async def test_reject_marks_preview_rejected(db_session):
    run = CompactionRun(
        status=STATUS_PREVIEW,
        groups_json=[{"canonical": "a", "aliases": ["b"]}],
    )
    db_session.add(run)
    await db_session.commit()

    await CompactionService(db_session).reject(run.id)
    await db_session.commit()

    refreshed = await db_session.get(CompactionRun, run.id)
    assert refreshed.status == STATUS_REJECTED


async def test_worker_apply_returns_404_for_unknown_run(db_session):
    """POST /compact/apply with a bogus id surfaces as 404, not a phantom 202.

    Uses ``httpx.AsyncClient`` with an ASGI transport (rather than
    ``TestClient``) so the handler runs on the same event loop as the
    asyncpg pool the fixture warmed up — TestClient spawns its own loop
    and corrupts the connection state.
    """
    import uuid as _uuid

    import httpx

    from niouzou.workers import refresh_worker as rw

    transport = httpx.ASGITransport(app=rw.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/compact/apply", json={"id": str(_uuid.uuid4())})
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


async def test_worker_apply_returns_409_for_terminal_state(db_session):
    """Applied / rejected / failed runs can't be re-applied."""
    import httpx

    from niouzou.workers import refresh_worker as rw

    run = CompactionRun(
        status=STATUS_APPLIED,
        groups_json=[{"canonical": "a", "aliases": ["b"]}],
    )
    db_session.add(run)
    await db_session.commit()

    transport = httpx.ASGITransport(app=rw.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/compact/apply", json={"id": str(run.id)})
    assert resp.status_code == 409
    assert resp.json()["error"] == "invalid_state"


async def test_preview_filters_hallucinated_terms(db_session):
    """Groups referencing terms not in the vocab snapshot are dropped."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.9)
    await db_session.commit()

    # FakeClient yields the same string for every call; the prompt itself is
    # built internally by CompactionService.
    client = FakeClient(
        [
            # Both the canonical and one alias are not in the vocab — drop the
            # group entirely rather than risk renaming rows we never saw.
            '{"groups": [{"canonical": "rust language", "aliases": ["rust", "rustlang"]}]}'
        ]
    )
    svc = CompactionService(db_session, client)
    run = await svc.preview()
    await db_session.commit()
    # Preview is persisted but empty (hallucination filtered out). Admin sees
    # "no groups to merge" rather than a destructive proposal.
    assert run.groups_json == []
    assert run.status == STATUS_PREVIEW
