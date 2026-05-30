"""Stats schema (GET /stats, E7-S15)."""

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


class EnrichmentStats(BaseModel):
    last_enriched_at: datetime | None
    total_ai: int
    # All TF-IDF enrichments (fallback + pure when AI is off). Lets the PWA
    # show a non-zero TF-IDF count even when AI was never attempted.
    total_tfidf: int
    total_tfidf_fallback: int
    last_error: str | None
    last_error_at: datetime | None


class Stats(BaseModel):
    # Surfaced so the PWA can render the "Next fetch" countdown (E7-S27)
    # against the live setting rather than a hardcoded number — also tracks
    # changes made via /admin/config (E8-S3).
    cron_fetch_interval_minutes: int
    articles: ArticlesStats
    sources: SourcesStats
    keywords: KeywordsStats
    enrichment: EnrichmentStats
