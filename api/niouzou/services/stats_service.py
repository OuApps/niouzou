"""Stats aggregator (GET /stats, E7-S15, E10-S1).

Per-user counts (articles, sources, keywords, enrichment) come from existing
tables scoped via the user→source→article ownership chain. The ``pipeline``
block is global: the refresh worker is single-replica and the
``pipeline_runs`` history is shared by the whole instance.
"""

import uuid

from sqlalchemy import case, func, select, text

from niouzou.deps import SessionDep
from niouzou.models import (
    Article,
    ArticleFeedback,  # noqa: F401  (kept for future enrichment stats)
    ArticleKeyword,
    CompactionRun,
    KeywordWeight,
    PipelineRun,
    Source,
)
from niouzou.models.compaction_run import STATUS_APPLIED, STATUS_PREVIEW
from niouzou.models.article import STATUS_ENRICHED
from niouzou.models.pipeline_run import STATUS_RUNNING
from niouzou.schemas.stats import (
    ArticlesStats,
    EnrichmentStats,
    KeywordsStats,
    PipelineProgress,
    PipelineStats,
    SourcesStats,
    Stats,
)
from niouzou.services.settings_service import SettingsService


class StatsService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> Stats:
        # E8-S3: the PWA renders "Next run" against this value, so read it
        # via SettingsService — admin overrides via PATCH /admin/config flow
        # through immediately.
        fetch_interval = await SettingsService(self.session).get(
            "cron_fetch_interval"
        )
        # ── Articles (scoped to user's sources, ignoring soft-deleted) ────
        article_join = (
            select(Article)
            .join(Source, Source.id == Article.source_id)
            .where(Source.user_id == user_id, Source.deleted_at.is_(None))
        ).subquery()

        articles_row = (
            await self.session.execute(
                select(
                    func.count().label("total"),
                    func.count(
                        case(
                            (article_join.c.status != STATUS_ENRICHED, 1)
                        )
                    ).label("pending"),
                    func.max(article_join.c.created_at).label("last_fetched_at"),
                    func.max(article_join.c.enriched_at).label("last_enriched_at"),
                    func.count(
                        case((article_join.c.enrichment_method == "ai", 1))
                    ).label("total_ai"),
                    func.count(
                        case((article_join.c.enrichment_method == "tfidf", 1))
                    ).label("total_tfidf"),
                    func.count(
                        case(
                            (
                                (article_join.c.enrichment_method == "tfidf")
                                & (article_join.c.enrichment_error.is_not(None)),
                                1,
                            )
                        )
                    ).label("total_tfidf_fallback"),
                ).select_from(article_join)
            )
        ).one()

        # ── Last enrichment error (most recent non-null, ≤ 1 h old) ────────
        # ``articles.enrichment_error`` is per-article and persists until the
        # row is re-enriched — without the time window an error from 3 h ago
        # would still flag the System panel as broken even after a dozen
        # healthy runs. 1 h matches the typical ``cron_fetch_interval`` (15
        # min) × ~4 runs of recovery time: long enough to be diagnostic, short
        # enough not to be noise. Recurring errors will keep being detected on
        # each new failed enrichment.
        last_err_row = (
            await self.session.execute(
                select(
                    article_join.c.enrichment_error,
                    article_join.c.enriched_at,
                )
                .where(article_join.c.enrichment_error.is_not(None))
                .where(
                    article_join.c.enriched_at
                    > func.now() - text("interval '1 hour'")
                )
                .order_by(article_join.c.enriched_at.desc())
                .limit(1)
            )
        ).first()

        # ── Sources ────────────────────────────────────────────────────────
        sources_total = await self.session.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.user_id == user_id, Source.deleted_at.is_(None))
        )
        # "active" mirrors total today — no per-source disable flag yet. Kept
        # as a separate field in the response so the PWA contract doesn't
        # change when that distinction is introduced.
        sources_active = sources_total

        # ── Keywords ───────────────────────────────────────────────────────
        keywords_row = (
            await self.session.execute(
                select(
                    func.count().label("total"),
                    func.count(
                        case((KeywordWeight.manually_overridden.is_(True), 1))
                    ).label("overridden"),
                ).where(KeywordWeight.user_id == user_id)
            )
        ).one()

        # ── Compaction telemetry (global, E10-S3) ─────────────────────────
        distinct_keyword_count = (
            await self.session.scalar(
                select(func.count(func.distinct(ArticleKeyword.term)))
            )
        ) or 0
        last_compact_at = await self.session.scalar(
            select(func.max(CompactionRun.applied_at)).where(
                CompactionRun.status == STATUS_APPLIED
            )
        )
        pending_preview_id = await self.session.scalar(
            select(CompactionRun.id)
            .where(CompactionRun.status == STATUS_PREVIEW)
            .order_by(CompactionRun.created_at.desc())
            .limit(1)
        )

        # ── Pipeline (global, E10-S1) ──────────────────────────────────────
        pipeline = await self._latest_pipeline()

        return Stats(
            cron_fetch_interval_minutes=int(fetch_interval or 15),
            articles=ArticlesStats(
                total=articles_row.total or 0,
                pending_enrichment=articles_row.pending or 0,
                last_fetched_at=articles_row.last_fetched_at,
            ),
            sources=SourcesStats(
                total=sources_total or 0,
                active=sources_active or 0,
            ),
            keywords=KeywordsStats(
                total=keywords_row.total or 0,
                manually_overridden=keywords_row.overridden or 0,
                distinct_keyword_count=distinct_keyword_count,
                last_compact_at=last_compact_at,
                pending_compaction_id=(
                    str(pending_preview_id) if pending_preview_id else None
                ),
            ),
            enrichment=EnrichmentStats(
                last_enriched_at=articles_row.last_enriched_at,
                total_ai=articles_row.total_ai or 0,
                total_tfidf=articles_row.total_tfidf or 0,
                total_tfidf_fallback=articles_row.total_tfidf_fallback or 0,
                last_error=last_err_row.enrichment_error if last_err_row else None,
                last_error_at=last_err_row.enriched_at if last_err_row else None,
            ),
            pipeline=pipeline,
        )

    async def _latest_pipeline(self) -> PipelineStats:
        """Read the most recent ``pipeline_runs`` row, or a synthetic neverrun.

        ``in_progress`` is populated only when the latest run is still
        ``'running'`` — outside that window the PWA shows the last result
        instead of a progress bar.

        On upgrade from a pre-E10-S1 instance the table is empty until the
        first new cron tick (≤ ``cron_fetch_interval`` minutes after worker
        restart). ``status='never_run'`` is returned in that window — the
        PWA falls back to ``articles.last_fetched_at`` so the System panel
        isn't a wall of dashes during that transient gap.
        """
        row = await self.session.scalar(
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(1)
        )
        if row is None:
            return PipelineStats(
                status="never_run",
                started_at=None,
                completed_at=None,
                articles_fetched=0,
                articles_enriched=0,
                articles_failed=0,
                total_duration_s=None,
                avg_s_per_article=None,
                error=None,
                in_progress=None,
            )
        in_progress = None
        if row.status == STATUS_RUNNING:
            done = (row.articles_enriched or 0) + (row.articles_failed or 0)
            in_progress = PipelineProgress(
                done=done,
                total=row.articles_in_run or 0,
            )
        return PipelineStats(
            status=row.status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            articles_fetched=row.articles_fetched or 0,
            articles_enriched=row.articles_enriched or 0,
            articles_failed=row.articles_failed or 0,
            total_duration_s=row.total_duration_s,
            avg_s_per_article=row.avg_s_per_article,
            error=row.error,
            in_progress=in_progress,
        )
