"""Tests for E10-S1 — pipeline_runs lifecycle, reaper, LLM retry, /stats.

DB-backed tests skip cleanly when Postgres is unreachable (via the shared
``db_session`` fixture). The refresh-worker test exercises the full pipeline
loop with a stub ``cron_fetch`` and ``cron_enrich.enrich_article`` so we
don't touch the LLM or newspaper paths.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from niouzou.models import Article, PipelineRun
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
            '{"summary_short": "Punchy.", "summary_executive": "- a\\n- b", '
            '"keywords": [{"term": "rust", "salience": 0.9}]}',
        ]
    )
    svc = EnrichmentService(client)
    result = svc.generate_enrichment("Title", "Some real content here.")
    assert client.calls == 2
    assert result.summary_short == "Punchy."
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
            '{"summary_short": "Punchy.", "summary_executive": null, '
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


# ── Refresh worker — pipeline_runs lifecycle end-to-end ─────────────────────


@pytest.mark.asyncio
async def test_run_pipeline_records_completed_with_counters(db_session, monkeypatch):
    """A clean fetch+enrich cycle produces a 'completed' run with counters."""
    import niouzou.workers.refresh_worker as rw
    from niouzou.crons import enrich as cron_enrich
    from niouzou.crons import fetch as cron_fetch

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
        ai_scoring = None
        tfidf_scoring = None
        openrouter_model = None

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_resources():
        yield _Stub()

    monkeypatch.setattr(cron_enrich, "enrichment_resources", _fake_resources)

    async def _fake_enrich(session, article, **_kw):
        article.status = STATUS_ENRICHED
        article.enrichment_method = "tfidf"

    monkeypatch.setattr(cron_enrich, "enrich_article", _fake_enrich)

    await rw._run_pipeline()

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
    import niouzou.workers.refresh_worker as rw
    from niouzou.crons import enrich as cron_enrich
    from niouzou.crons import fetch as cron_fetch

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
        ai_scoring = None
        tfidf_scoring = None
        openrouter_model = None

    @asynccontextmanager
    async def _fake_resources():
        yield _Stub()

    monkeypatch.setattr(cron_enrich, "enrichment_resources", _fake_resources)

    async def _exploding_enrich(session, article, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(cron_enrich, "enrich_article", _exploding_enrich)

    await rw._run_pipeline()

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
    import niouzou.workers.refresh_worker as rw
    from niouzou.crons import fetch as cron_fetch

    user = await make_user(db_session)
    await make_source(db_session, user)
    await db_session.commit()

    async def _exploding_fetch() -> int:
        raise RuntimeError("miniflux down")

    monkeypatch.setattr(cron_fetch, "run", _exploding_fetch)

    await rw._run_pipeline()

    run = await db_session.scalar(
        select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
    )
    assert run is not None
    assert run.status == STATUS_FAILED
    assert run.error is not None
    assert "miniflux down" in run.error
