"""Tests for E10-S1 — pipeline_runs lifecycle, reaper, LLM retry, /stats.

DB-backed tests skip cleanly when Postgres is unreachable (via the shared
``db_session`` fixture). The refresh-worker test exercises the full pipeline
loop with a stub ``cron_fetch`` and ``cron_enrich.enrich_article`` so we
don't touch the LLM or newspaper paths.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from niouzou.models import Article, LLMUsageLog, PipelineRun
from niouzou.models.article import STATUS_ENRICHED, STATUS_ENRICHING, STATUS_PENDING
from niouzou.models.pipeline_run import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
)
from niouzou.services.enrichment_service import EnrichmentService
from niouzou.services.openrouter_client import OpenRouterError
from tests.factories import make_article, make_source, make_user
from tests.test_ai_keyword import FakeClient


# ── EnrichmentService — LLM retry policy (E10-S1) ───────────────────────────


def test_generate_enrichment_retries_twice_before_fallback(monkeypatch):
    """3 failures → fallback Enrichment with keywords=None (TF-IDF path)."""
    # Don't wait for real backoffs; the test would take 4s otherwise.
    monkeypatch.setattr("niouzou.services.enrichment_service.time.sleep", lambda _: None)
    client = FakeClient(
        [
            OpenRouterError("rate limited"),
            OpenRouterError("timeout"),
            OpenRouterError("still broken"),
        ]
    )
    svc = EnrichmentService(client)
    result = svc.generate_enrichment("Title", "Some real content here.")
    assert client.calls == 3
    assert result.keywords is None  # signals fallback to cron
    assert result.summary_executive is None


def test_generate_enrichment_succeeds_on_second_attempt(monkeypatch):
    """One transient failure must not poison the run — second try wins."""
    monkeypatch.setattr("niouzou.services.enrichment_service.time.sleep", lambda _: None)
    client = FakeClient(
        [
            OpenRouterError("transient blip"),
            '{"summary_executive": "- a\\n- b", '
            '"keywords": [{"term": "rust", "salience": 0.9}]}',
        ]
    )
    svc = EnrichmentService(client)
    result = svc.generate_enrichment("Title", "Some real content here.")
    assert client.calls == 2
    assert result.summary_executive == "- a\n- b"
    assert result.keywords is not None
    assert [k.term for k in result.keywords] == ["rust"]


def test_generate_enrichment_succeeds_first_try_no_retry(monkeypatch):
    """Clean reply on the first call must not trigger any retry/backoff."""
    sleeps: list[float] = []
    monkeypatch.setattr(
        "niouzou.services.enrichment_service.time.sleep", lambda s: sleeps.append(s)
    )
    client = FakeClient(
        [
            '{"summary_executive": "- a\\n- b", '
            '"keywords": [{"term": "rust", "salience": 0.9}]}',
        ]
    )
    svc = EnrichmentService(client)
    svc.generate_enrichment("Title", "Some real content here.")
    assert client.calls == 1
    assert sleeps == []  # no backoff invoked


# ── Reaper — articles stuck in 'enriching' are reset on startup ─────────────


@pytest.mark.asyncio
async def test_reaper_resets_enriching_to_pending(db_session):
    """A worker crash mid-enrichment leaves an article 'enriching'; the
    reaper at the next startup must reset it to 'pending' so the next run
    picks it up."""
    from niouzou.workers.refresh_worker import _reaper_reset_enriching

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    stuck = await make_article(db_session, source, status=STATUS_ENRICHING)
    enriched = await make_article(db_session, source, status=STATUS_ENRICHED)
    pending = await make_article(db_session, source, status=STATUS_PENDING)
    await db_session.commit()  # commit so the helper's own session sees it

    count = await _reaper_reset_enriching()
    assert count == 1

    # Reload — the helper opened its own session_scope, so refresh ours.
    await db_session.refresh(stuck)
    await db_session.refresh(enriched)
    await db_session.refresh(pending)
    assert stuck.status == STATUS_PENDING
    assert enriched.status == STATUS_ENRICHED  # unchanged
    assert pending.status == STATUS_PENDING  # unchanged


# ── /stats — pipeline block lifecycle ───────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_pipeline_never_run(db_session):
    """Empty pipeline_runs table → synthetic 'never_run' status, no in_progress."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    await db_session.commit()
    svc = StatsService(db_session)
    stats = await svc.get(user.id)
    assert stats.pipeline.status == "never_run"
    assert stats.pipeline.started_at is None
    assert stats.pipeline.in_progress is None


@pytest.mark.asyncio
async def test_stats_pipeline_running_exposes_progress(db_session):
    """While a run is in flight, in_progress is populated from the row."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    db_session.add(
        PipelineRun(
            status=STATUS_RUNNING,
            articles_in_run=10,
            articles_enriched=4,
            articles_failed=1,
        )
    )
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    assert stats.pipeline.status == STATUS_RUNNING
    assert stats.pipeline.in_progress is not None
    # done = enriched + failed = 5; total = articles_in_run = 10
    assert stats.pipeline.in_progress.done == 5
    assert stats.pipeline.in_progress.total == 10


@pytest.mark.asyncio
async def test_stats_pipeline_completed_no_progress(db_session):
    """A finished run reports counters but no in_progress block."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    db_session.add(
        PipelineRun(
            status=STATUS_COMPLETED,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=3),
            completed_at=datetime.now(timezone.utc),
            articles_fetched=8,
            articles_enriched=7,
            articles_failed=1,
            articles_in_run=8,
            total_duration_s=180.0,
            avg_s_per_article=25.7,
        )
    )
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    assert stats.pipeline.status == STATUS_COMPLETED
    assert stats.pipeline.articles_enriched == 7
    assert stats.pipeline.articles_failed == 1
    assert stats.pipeline.total_duration_s == 180.0
    assert stats.pipeline.in_progress is None


@pytest.mark.asyncio
async def test_stats_returns_most_recent_run(db_session):
    """When multiple runs exist, /stats reads the latest by started_at."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        PipelineRun(
            status=STATUS_COMPLETED,
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=1, minutes=55),
            articles_enriched=3,
        )
    )
    db_session.add(
        PipelineRun(
            status=STATUS_FAILED,
            started_at=now - timedelta(minutes=10),
            completed_at=now - timedelta(minutes=8),
            error="OpenRouterError: 503",
        )
    )
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    # Latest by started_at is the failed one.
    assert stats.pipeline.status == STATUS_FAILED
    assert stats.pipeline.error == "OpenRouterError: 503"


# ── /stats — windowed pipeline aggregates (E10-S5) ──────────────────────────


@pytest.mark.asyncio
async def test_stats_pipeline_aggregates_default_window_is_6h(db_session):
    """Default window is 6 h and only counts runs inside it."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    now = datetime.now(timezone.utc)
    # Inside the 6 h default window:
    db_session.add(
        PipelineRun(
            status=STATUS_COMPLETED,
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1) + timedelta(minutes=2),
            articles_fetched=5,
            articles_enriched=5,
            articles_failed=0,
            total_duration_s=100.0,
        )
    )
    # Outside the window — must not contribute:
    db_session.add(
        PipelineRun(
            status=STATUS_COMPLETED,
            started_at=now - timedelta(hours=10),
            completed_at=now - timedelta(hours=10) + timedelta(minutes=5),
            articles_fetched=99,
            articles_enriched=99,
            articles_failed=9,
            total_duration_s=9999.0,
        )
    )
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    agg = stats.pipeline.aggregates
    assert agg.window_hours == 6
    assert agg.runs_count == 1
    assert agg.articles_fetched == 5
    assert agg.articles_enriched == 5
    assert agg.articles_failed == 0
    assert agg.avg_s_per_article == pytest.approx(100.0 / 5)


@pytest.mark.asyncio
async def test_stats_pipeline_aggregates_1h_window_excludes_older(db_session):
    """``pipeline_window=1h`` drops the 2-h-old run."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        PipelineRun(
            status=STATUS_COMPLETED,
            started_at=now - timedelta(minutes=20),
            completed_at=now - timedelta(minutes=18),
            articles_fetched=3,
            articles_enriched=3,
            total_duration_s=60.0,
        )
    )
    db_session.add(
        PipelineRun(
            status=STATUS_COMPLETED,
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2) + timedelta(minutes=2),
            articles_fetched=10,
            articles_enriched=10,
            total_duration_s=200.0,
        )
    )
    await db_session.commit()
    stats = await StatsService(db_session).get(
        user.id, pipeline_window="1h"
    )
    agg = stats.pipeline.aggregates
    assert agg.window_hours == 1
    assert agg.runs_count == 1
    assert agg.articles_enriched == 3


@pytest.mark.asyncio
async def test_stats_pipeline_aggregates_avg_is_weighted_by_articles(db_session):
    """``avg_s_per_article`` weights by articles, not by run."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    now = datetime.now(timezone.utc)
    # Run A: 10 articles at 30 s/article → 300 s total
    db_session.add(
        PipelineRun(
            status=STATUS_COMPLETED,
            started_at=now - timedelta(minutes=30),
            completed_at=now - timedelta(minutes=25),
            articles_fetched=10,
            articles_enriched=10,
            total_duration_s=300.0,
        )
    )
    # Run B: 1 article at 60 s/article → 60 s total
    db_session.add(
        PipelineRun(
            status=STATUS_COMPLETED,
            started_at=now - timedelta(minutes=10),
            completed_at=now - timedelta(minutes=9),
            articles_fetched=1,
            articles_enriched=1,
            total_duration_s=60.0,
        )
    )
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    agg = stats.pipeline.aggregates
    # Weighted: (300+60) / (10+1) ≈ 32.7. Arithmetic mean of run-level
    # averages would be (30+60)/2 = 45, which we explicitly avoid.
    assert agg.avg_s_per_article == pytest.approx(360 / 11)


@pytest.mark.asyncio
async def test_stats_pipeline_aggregates_null_avg_when_no_completed_runs(db_session):
    """No ``completed`` runs in the window → avg_s_per_article is null."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    now = datetime.now(timezone.utc)
    # Only running and failed runs in window — must be excluded from the
    # weighted average so a half-finished or zero-duration row can't drag
    # it down.
    db_session.add(
        PipelineRun(
            status=STATUS_RUNNING,
            started_at=now - timedelta(minutes=5),
            articles_in_run=10,
            articles_enriched=2,
        )
    )
    db_session.add(
        PipelineRun(
            status=STATUS_FAILED,
            started_at=now - timedelta(minutes=15),
            completed_at=now - timedelta(minutes=14),
            error="boom",
        )
    )
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    agg = stats.pipeline.aggregates
    assert agg.runs_count == 0
    assert agg.articles_enriched == 0
    assert agg.avg_s_per_article is None


@pytest.mark.asyncio
async def test_stats_pipeline_aggregates_zero_when_no_runs(db_session):
    """Empty table → counters at 0, null avg, runs_count 0."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    agg = stats.pipeline.aggregates
    assert agg.runs_count == 0
    assert agg.articles_fetched == 0
    assert agg.articles_enriched == 0
    assert agg.articles_failed == 0
    assert agg.avg_s_per_article is None


@pytest.mark.asyncio
async def test_stats_pipeline_window_validation_rejects_unknown_value():
    """``?pipeline_window=2h`` → 422 (Literal type rejects it at the edge).

    Uses ``httpx.AsyncClient`` + ASGITransport (same pattern as
    ``test_compaction.py``) — ``TestClient`` spawns its own event loop and
    corrupts the asyncpg pool that other tests share. The route never
    reaches its body since validation fires first, so no DB / auth setup
    is needed here.
    """
    import uuid as _uuid

    import httpx

    from niouzou.deps import get_current_user
    from niouzou.main import app

    class _FakeUser:
        id = _uuid.uuid4()
        # E19-S7 — /stats is admin-only now; this test exercises the query-param
        # validation path, so the fake user must clear the admin gate.
        is_admin = True

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            resp = await client.get(
                "/api/v1/stats", params={"pipeline_window": "2h"}
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_stats_is_admin_only_but_freshness_is_open():
    """E19-S7 — a non-admin gets 403 on /stats but 200 on /stats/freshness.

    Same ASGITransport pattern. The non-admin /stats call is rejected by the
    ``get_current_admin`` gate before any DB access, so no setup is needed;
    the freshness call does hit the DB, so it's only asserted when Postgres
    is reachable.
    """
    import uuid as _uuid

    import httpx

    from niouzou.db import engine
    from niouzou.deps import get_current_user
    from niouzou.main import app

    class _NonAdmin:
        id = _uuid.uuid4()
        is_admin = False

    app.dependency_overrides[get_current_user] = lambda: _NonAdmin()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            stats_resp = await client.get("/api/v1/stats")
            assert stats_resp.status_code == 403

            # Freshness touches the DB — skip the assertion if it's unreachable.
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                reachable = True
            except Exception:
                reachable = False
            if reachable:
                fresh_resp = await client.get("/api/v1/stats/freshness")
                assert fresh_resp.status_code == 200
                body = fresh_resp.json()
                assert "pipeline_status" in body
                assert "pending_enrichment" in body
                assert "last_completed_at" in body
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ── /stats — OpenRouter cost aggregates (E10-S7) ────────────────────────────


@pytest.mark.asyncio
async def test_stats_llm_cost_windows_sum_by_age(db_session):
    """Rows at various ages contribute to the windows that contain them."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            LLMUsageLog(
                created_at=now - timedelta(minutes=30),
                model="m",
                cost_usd=0.001,
            ),
            LLMUsageLog(
                created_at=now - timedelta(hours=3),
                model="m",
                cost_usd=0.01,
            ),
            LLMUsageLog(
                created_at=now - timedelta(hours=12),
                model="m",
                cost_usd=0.1,
            ),
            LLMUsageLog(
                created_at=now - timedelta(hours=30),
                model="m",
                cost_usd=1.0,
            ),
        ]
    )
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    by_window = {w.window_hours: w.cost_usd for w in stats.llm_cost.windows}
    assert by_window[1] == pytest.approx(0.001)
    assert by_window[6] == pytest.approx(0.001 + 0.01)
    assert by_window[24] == pytest.approx(0.001 + 0.01 + 0.1)


@pytest.mark.asyncio
async def test_stats_llm_cost_windows_zero_when_no_rows(db_session):
    """Empty llm_usage_log → all windows at 0."""
    from niouzou.services.stats_service import StatsService

    user = await make_user(db_session)
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    assert [w.cost_usd for w in stats.llm_cost.windows] == [0.0, 0.0, 0.0]
    assert [w.window_hours for w in stats.llm_cost.windows] == [1, 6, 24]


# ── Refresh worker — pipeline_runs lifecycle end-to-end ─────────────────────


@pytest.mark.asyncio
async def test_run_pipeline_records_completed_with_counters(db_session, monkeypatch):
    """A clean fetch+enrich cycle produces a 'completed' run with counters."""
    from niouzou.crons import enrich as cron_enrich
    from niouzou.crons import fetch as cron_fetch
    from niouzou.crons import run_once

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    # Two pending articles to enrich.
    a1 = await make_article(db_session, source, status=STATUS_PENDING)
    a2 = await make_article(db_session, source, status=STATUS_PENDING)
    await db_session.commit()

    # Stub cron_fetch — pretend two new entries were ingested.
    async def _fake_fetch() -> int:
        return 2

    monkeypatch.setattr(cron_fetch, "run", _fake_fetch)

    # Stub enrichment_resources — yield None instances, enrich_article is stubbed too.
    class _Stub:
        enrichment = None
        scoring = None
        openrouter_model = None
        embedder = None

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_resources():
        yield _Stub()

    monkeypatch.setattr(cron_enrich, "enrichment_resources", _fake_resources)

    async def _fake_enrich(session, article, **_kw):
        article.status = STATUS_ENRICHED
        article.enrichment_method = "ai"

    monkeypatch.setattr(cron_enrich, "enrich_article", _fake_enrich)

    await run_once._run_pipeline()

    # Latest run should be 'completed' with counters set.
    run = await db_session.scalar(
        select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
    )
    assert run is not None
    assert run.status == STATUS_COMPLETED
    assert run.articles_fetched == 2
    assert run.articles_in_run == 2
    assert run.articles_enriched == 2
    assert run.articles_failed == 0
    assert run.completed_at is not None
    assert run.total_duration_s is not None
    assert run.error is None

    # Both articles ended up enriched.
    await db_session.refresh(a1)
    await db_session.refresh(a2)
    assert a1.status == STATUS_ENRICHED
    assert a2.status == STATUS_ENRICHED


@pytest.mark.asyncio
async def test_run_pipeline_counts_failed_and_resets_status(
    db_session, monkeypatch
):
    """An uncaught exception in enrich_article increments articles_failed and
    rolls the article back to pending."""
    from niouzou.crons import enrich as cron_enrich
    from niouzou.crons import fetch as cron_fetch
    from niouzou.crons import run_once

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, status=STATUS_PENDING)
    await db_session.commit()

    async def _fake_fetch() -> int:
        return 1

    monkeypatch.setattr(cron_fetch, "run", _fake_fetch)

    from contextlib import asynccontextmanager

    class _Stub:
        enrichment = None
        scoring = None
        openrouter_model = None
        embedder = None

    @asynccontextmanager
    async def _fake_resources():
        yield _Stub()

    monkeypatch.setattr(cron_enrich, "enrichment_resources", _fake_resources)

    async def _exploding_enrich(session, article, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(cron_enrich, "enrich_article", _exploding_enrich)

    await run_once._run_pipeline()

    run = await db_session.scalar(
        select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
    )
    assert run is not None
    # The pipeline itself completed — only one article failed (still a run
    # the operator can interpret; 'failed' is reserved for global aborts).
    assert run.status == STATUS_COMPLETED
    assert run.articles_failed == 1
    assert run.articles_enriched == 0

    await db_session.refresh(article)
    # Reset back to pending so the next run picks it up.
    assert article.status == STATUS_PENDING


@pytest.mark.asyncio
async def test_run_pipeline_marks_failed_when_fetch_raises(
    db_session, monkeypatch
):
    """A global exception (cron_fetch raises) → status='failed' with error."""
    from niouzou.crons import fetch as cron_fetch
    from niouzou.crons import run_once

    user = await make_user(db_session)
    await make_source(db_session, user)
    await db_session.commit()

    async def _exploding_fetch() -> int:
        raise RuntimeError("miniflux down")

    monkeypatch.setattr(cron_fetch, "run", _exploding_fetch)

    await run_once._run_pipeline()

    run = await db_session.scalar(
        select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
    )
    assert run is not None
    assert run.status == STATUS_FAILED
    assert run.error is not None
    assert "miniflux down" in run.error
