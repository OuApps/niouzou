"""Stats schema (GET /stats, E7-S15, E10-S1)."""

from datetime import datetime

from pydantic import BaseModel


class ArticlesStats(BaseModel):
    total: int
    pending_enrichment: int
    last_fetched_at: datetime | None


class SourcesStats(BaseModel):
    total: int
    active: int


class KeywordsStats(BaseModel):
    total: int
    manually_overridden: int
    # E10-S3 — global vocab size + compaction lifecycle for the admin panel.
    # ``distinct_keyword_count`` is the number of distinct rows in
    # ``article_keywords.term`` (instance-wide); ``last_compact_at`` is the
    # most recent ``applied_at`` on ``compaction_runs``; ``pending_compaction_id``
    # is the most recent preview that hasn't been applied or rejected — used
    # by the admin to resume an abandoned analysis.
    distinct_keyword_count: int = 0
    last_compact_at: datetime | None = None
    pending_compaction_id: str | None = None


class EnrichmentStats(BaseModel):
    last_enriched_at: datetime | None
    total_ai: int
    # All TF-IDF enrichments (fallback + pure when AI is off). Lets the PWA
    # show a non-zero TF-IDF count even when AI was never attempted.
    total_tfidf: int
    total_tfidf_fallback: int
    last_error: str | None
    last_error_at: datetime | None


class PipelineProgress(BaseModel):
    """Live progress inside a currently-running pipeline cycle.

    Populated only when the latest ``pipeline_run`` has ``status='running'``.
    ``done`` includes both successfully-enriched and failed articles so the
    bar reaches ``total`` even when some articles error out.
    """

    done: int
    total: int


class PipelineAggregates(BaseModel):
    """Pipeline health summed over a configurable window (E10-S5).

    Replaces the old "last run" snapshot for the admin System panel: on an
    instance that ticks every 15 min, the previous run was a 1-2 article
    photo that bounced wildly; the windowed sum lets the user gauge the
    pipeline's actual recent health.

    ``avg_s_per_article`` is weighted by ``articles_enriched`` per run (a
    10-article run at 30 s contributes 10× more than a 1-article run at
    60 s) — a plain arithmetic mean of run-level averages would over-weight
    near-empty cycles.
    """

    window_hours: int
    runs_count: int
    articles_fetched: int
    articles_enriched: int
    articles_failed: int
    avg_s_per_article: float | None


class PipelineStats(BaseModel):
    """Most recent fetch+enrich cycle (E10-S1) + windowed aggregates (E10-S5).

    Global — not user-scoped. The whole instance shares one refresh worker
    and one ``pipeline_runs`` history; per-user telemetry would be
    misleading since the worker doesn't enrich on behalf of a single user.

    ``status='never_run'`` is synthetic: returned when the table is empty
    (fresh install), so the PWA can render an "instance just booted" state
    instead of confusing missing fields.
    """

    status: str
    started_at: datetime | None
    completed_at: datetime | None
    articles_fetched: int
    articles_enriched: int
    articles_failed: int
    total_duration_s: float | None
    avg_s_per_article: float | None
    error: str | None
    in_progress: PipelineProgress | None
    aggregates: PipelineAggregates


class Stats(BaseModel):
    # Surfaced so the PWA can render the "Next run" countdown
    # against the live setting rather than a hardcoded number. Tracks
    # changes made via /admin/config (E8-S3, E10-S1).
    cron_fetch_interval_minutes: int
    # E11-S1 — effective ``SCORE_THRESHOLD`` (DB override else env var).
    # Lets the Explore filter bar render the "≥ seuil" chip with the
    # real value instead of hardcoding it.
    score_threshold: float
    articles: ArticlesStats
    sources: SourcesStats
    keywords: KeywordsStats
    enrichment: EnrichmentStats
    # Global pipeline telemetry — drives the PWA System panel (E10-S1).
    pipeline: PipelineStats
